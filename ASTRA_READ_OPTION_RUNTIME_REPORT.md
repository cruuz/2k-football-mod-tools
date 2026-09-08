# ASTRA read-option runtime report, 2026-09-06

EXPERIMENTAL / UNWITNESSED. Branch `astra/r62-read-option-runtime`, based on
`f371972f4a17cecf654c019d5c6ff3a3c32c7caa`. No gameplay has been witnessed by
Noah for this change. Basic, Advanced and Experimental must all leave it off.

The bounded runtime core is implemented and passes the two XBE gates, the
manifest tests, and standalone authoring/instruction tests. It supports paired
authored Zone read and RPO records, modern release-to-give/hold-to-keep input,
a CPU EDGE position/velocity decision, and one latched condition-task result
shared with the back through the existing native branch cache.

**The complete dependable-read brief is not implemented.** The requested
human read-window prompt and live search for a replacement unblocked EDGE are
absent. The assembled core uses the entire authorized 1,024-byte owner budget:
960 RX bytes, including eight constant bytes, plus 64 immutable table bytes.
There is no new RW allocation or spare byte in this owner. I retained these
limits instead of taking another owner's budget. A complete prompt, live role
resolver and richer lifecycle/sampling state need a revised implementation or
explicitly revised budget. Protected product integration is specified in
[WIRING.md](WIRING.md), not installed here.

RPO's third result means entering the native pass continuation after the
intended receiver passes the retail readiness check. It is **not proof of an
immediate throw**, an instruction to the final throw helper, or a guarantee
that a human receiver press during the mesh survives into the native passing
input mode. The native pass timer, selection and release still control that
part. The feature must not be advertised as a finished three-way mesh exchange.

**Delivered files and decisions.** The new core is
`mod_editor/core/nfl2k5_read_option_runtime.py`, with the reproducible checked-in
template `nfl2k5_read_option_runtime_code.py`, GNU source
`tools/nfl2k5_read_option_runtime.S`, and standard-library ELF32 assembler
driver `tools/nfl2k5_read_option_runtime_assemble.py`. End-user application
does not need GNU as, Capstone, Unicorn, research exports or test files.

`nfl2k5_play_library.compile_read_option_intent_table()` creates the separate
immutable artifact from exact final PLAY bytes paired with their existing
versioned compiler receipts. It does not edit PLAY. The existing option pack
and data-only authoring presets remain available. No PLAY opcode was added.
`tests/nfl2k5_allocator_stack.py`, the budget fixture, manifest builder owner
lists and both XBE gate compositions include the new canonical owner
`nfl2k5_read_option_runtime`. The capability handoff object is
`docs/mod_editor/nfl2k5_read_option_runtime_capability.json`, classified
`offline-writer-proved`, with runtime `not-tested` and explicit gaps.

**PROVED: identity, ownership and offline refusal.** The 64-byte table has a
16-byte `RDO1` header, version 1, row count and zero flags, followed by at most
two 24-byte records. Each record holds five little-endian dwords (book-name
FNV-1a, descriptor offset, QB-script FNV-1a, back-script FNV-1a, play-name
FNV-1a) and four bytes (back slot, authored read slot, intended receiver or zero,
zero flags). Rows are sorted, duplicate/colliding book-plus-offset keys refuse,
and unused padding must be zero. FNV is a bounded identity check, not a
cryptographic guarantee against deliberately constructed collisions.

The host compiler verifies the full replacement SHA-256 and
`nfl2k5_option_intent/v1` receipt, legal offensive play, paired branch/sync
graph, authored formation/personnel signature, two five-node participant
scripts, bounded names and table capacity. The condition's documented argument
must be 13, otherwise it could alias the new decision union. Native Speed option
records are excluded. Receiver slot 6 is refused for runtime RPO because its
A-button receiver request conflicts with the snap hold; slots 7 and 8 are
accepted. A stale/intermediate PLAY receipt must be recompiled after later
resource edits, never made to match by updating its hash alone.

The old MIN experimental fixtures did not both name an EDGE: Zone read's slot 2
is a DT and RPO's slot 6 is an off-ball OLB. The compiler uses the validated
authored defensive formation's DEs, or OLBs within two yards of the line, and
preserves a valid authored EDGE; otherwise it selects the extreme EDGE on the
run side. Both supplied recipes resolve to slot 1. The receipt records the
original and chosen slot. This is an **authored formation correction**, not
the missing live fallback. A different on-field front can put a different role
in that slot; runtime role/signature revalidation remains a gap.

At runtime, identity is restricted to QB actor slot 0, condition node 2,
aligned offensive descriptors in either relocated PLAY buffer at `0xB75A40`
or `0xB88DD0`, and the matching book, play name and both participant scripts.
Names and script reads are bounded to the native pools. The actual retail
loader runs in the fixtures before these checks. Nonmatching names, scripts,
actors, nodes or descriptors follow the displaced retail instructions.

The module pins the complete nine-byte hook at `0x1AF191` (file offset
`0x19F191`), `D9 47 60 D8 1D 80 41 4E 00`, and hashes the initializer, update,
native helpers and relevant controller tables. This is a live instruction
boundary, not a cave. `status()` returns retail/applied/foreign;
`apply()` validates before mutation, installs through `space.install_code`
and `space.install_read_only`, repins section digests and checks its result.
Mixed hooks, dependency changes, foreign code/table/seals, partial allocations
and changed explicit settings refuse. Replay with an omitted table retains the
installed table and changes zero bytes. Receipts contain the full hook edit,
allocation/install receipts, source/result/table hashes and exact changed-byte
count. `read_settings()` reports the installed table's count and policy.

The module CLI uses bounded XBE/table reads and exclusive new output creation:
`python3 -m mod_editor.core.nfl2k5_read_option_runtime status source.xbe` or
`apply source.xbe --output new.xbe --table compiled-intent.bin`. It does no
disc or pack I/O. A lower-level empty table deliberately installs a dormant
owner; the protected Build wiring must reject an enabled checkbox with no
paired read recipes.

**PROVED: instruction boundary and native state contract.** The hook runs after
native conditional movement, before the retail timer/threat gates. At that
boundary ESI is actor, EDI is task and ECX is interpreter; no new stack arguments
are consumed. The wrapper saves flags and GPRs, aligns and saves the 512-byte
FXSAVE area, initializes local x87 work, and restores the saved floating/SSE
state, stack, registers and flags. Its only intentional saved-register change
is EBX, the native condition result. Tagged paths join `0x1AF210`; bypass
replays both displaced x87 instructions and resumes `0x1AF19A`.

The runtime owns the meaning of the native condition's **documented argument
field** at task `+0x44`, which the actual initializer stores as float 13
(`0x41500000`). It does not appropriate retail task padding. First matched
update resolves and retains the selected actor in the documented native
target field `+0x40`, then marks the argument active (`0x41500001`). Pending
release is -1, pending pass request is -2; committed keep/give/pass are 0/1/2.
Committed values bypass later input and read-policy changes. These fields
already live in native writable task storage, never `.text`.

The native `0xBE4E28` condition cache is used for its existing participant-sync
purpose only: -1 wait, 0 release the back, 1 take the give branch. Result 2 is
kept in the condition argument and translates to native cache 0. RPO keep
sets interpreter terminal bit `0x20000` so `0x1AF292` enters the native carrying
exit; RPO pass takes its ordinary node-3 pass continuation. Give selects node 4.
The back's unchanged mode-6 condition reads the QB's native cache. No direct
ball-owner write, fake transfer, new writable global or stock pitch-bit rewrite
was added.

The actual initializer slice `0x1AF98D..0x1AF994` restores the argument; the
actual new-play slice `0x1AD9C0..0x1AD9DE` clears all 88 cache entries to -1.
Both run in the fixtures. This proves those named reset paths, not all audible,
substitution, no-huddle or save/reload paths. Task reconstruction outside the
tested normal lifecycle remains a witness requirement.

**PROVED: bounded human and CPU decisions.** The logical mesh boundary is the
float .35 in the since-snap clock at `[0xE6029C]+0x10`. Below it the participant
cache remains undecided. There is no animation/contact-derived mesh detector.
Dead phase waits; missing clock waits; lost ball ownership or invalid/stale
clock at or above five seconds selects a carrying exit without a new exchange.

The human path validates controller 0..3, layout 0..2 and running contexts 8/10.
It reads the live context table's physical column 0 and calls the actual
retail held-command reader `0x120960`, including its layout helper `0x77230`.
The pinned table gives the following mapping:

| Layout | Snap contexts 3/4, column 0 | Running contexts 8/10, same column |
| --- | --- | --- |
| 0 | command 3 | command 22 |
| 1 | command 3 | command 22 |
| 2 | command 3 | command 27 |

This column corresponds to held mask `0x100` in the retail controller state.
The test matrix covers all four controllers, three layouts, two contexts and
both held/released states at .349 and .35 seconds: 48 paired cases. This is
the held-state producer/table path, not the stock consumed pitch request at
`control+0x18`. Once release is observed, reholding cannot cancel a give; late
input and CPU-to-human takeover cannot change an already committed decision.
An intended RPO receiver's rising B/X mask can latch pass while snap is still
held; that request takes priority over subsequent release, but a release
already latched prevents a later pass. At the boundary the actual
`0x19B800` receiver-readiness function must succeed, otherwise the result is give.

For CPU controller -1, the authored slot is resolved through native `0x1894F0`
and retained. An offensive task targeting that EDGE disqualifies the read;
the scan is bounded to 11 actors and ignores the QB's own read target. This
is a conservative assignment-target check, not proof of physical block
engagement. Missing/blocked read or nonfinite/unbounded actor position/velocity
defaults give. There is no live replacement search.

The one-sample policy calls it a crash when lateral velocity points inward,
or downfield velocity points toward the authored mesh depth, and predicted
lateral separation after .2 seconds is at most 2.5 yards. Lane/depth signs use
the decoded mesh coordinates relative to the line, including both offensive
directions. A crash selects keep for Zone read or ready pass for RPO; stay,
widen or sufficiently distant movement selects give. This is newly authored
policy, not a recovered retail coaching rule. No multi-tick hysteresis or
sustained-motion filter fits this implementation.

**PROVED scope of tests; HYPOTHESIS beyond the boundary.** The installed
instructions, native PLAY loader, actor resolver, held-command reader,
receiver readiness, cache reader, native speed-option predicate and interpreter
advancement execute unstubbed. The fixture starts at the named post-movement
boundary with synthetic actor/task/ball state. Each added tick is bounded to
12,000 instructions; the retail loader to 60,000. The shared fixture records
movement/transition callees at entry with their cleanup ABI; tests stop at the
carrying transition where needed. Collision, full movement, transfer callbacks,
passing update, animation events and the game loop are not simulated.

The five retail speed options are excluded by compiler policy. The real MIN24
stock predicate/control executes native keep and pitch requests, including
preserving unrelated bits and advancing to the existing pitch node. Existing
data-tier tests cover the five branch-preserving stock options, authored pack
and the 9,251-play/37-book corpus. This is not a played lateral witness.

Retail defense, give/toss and throw-helper slices remain byte-identical:
`0x2FE190` (0x340 bytes), `0x2FD700` (0xE90), `0x2FF7C0` (0x230),
`0x300B00` (0x200), `0x1ACE40` (0x768) and `0x19BAE0` (0x80). These establish
no global defense/pitch/transfer rewrite. **Correct contain and pitch-man
responsibilities in play are unproved.** The memo's contain rush and reactive
coverage paths are not evidence of coordinated dive/QB/pitch assignments.
Expected failures to measure remain: two defenders chasing the owner and
abandoning the pitch back; coverage staying too long or leaving the pass route;
fake-induced pursuit changes; the read EDGE getting blocked; pressure delaying
a pitch until contact; wrong-time RPO coverage exchanges; invalid retained
targets after transfer/turnover/takeover; or an implausibly early defensive
reaction to internal branch state. Global pursuit, coverage and spy thresholds
were not changed to conceal those risks.

**Exact final verification.** All commands ran from this worktree with plain
standalone unittest entry points, with no skips or failures in these six files.
The three manifest-consuming commands used
`NFL2K5_CAVE_MANIFEST=.scratch/read-option/manifest.json`. `/usr/bin/time -v`
captured peak RSS except for the existing data-regression command.

| Command after `python3` | Result | unittest time | Peak RSS, KiB |
| --- | --- | --- | --- |
| `tests/mod_editor/test_nfl2k5_read_option_runtime.py` | 10 passed | 7.699 s | 282,484 |
| `tests/mod_editor/test_nfl2k5_read_option_unicorn.py` | 14 passed | 10.959 s | 987,372 |
| `tests/mod_editor/test_nfl2k5_read_option.py` | 15 passed | 9.822 s | not sampled |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 63 passed | 165.605 s | 294,028 |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 75 passed | 248.284 s | 469,932 |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed | 71.948 s | 917,776 |

Total: 205 tests. Both XBE gates include forward/reverse owner order and
scale-out cases. The new tests check complete instruction spans, no foreign
owner/interior entry at the hook, named immutable RX/RO permissions, indirect
native-state writes, table/PLAY pairing, mixed input refusal, exact receipts,
state/input commitment, both directions, missing/blocked reads, native resets,
RPO readiness/branch exits and relocation under the complete owner allocation
union. Byte-level gate success does not stand in for the witness list below.

Also passed: `python3 tools/nfl2k5_read_option_runtime_assemble.py --check`;
`python3 tools/nfl2k5_xbe_space.py plan --requests
tests/fixtures/nfl2k5_allocator_beta62_requests.json` (35 requests, supported
12,300,288-byte XBE); compilation of changed Python sources; and
`git diff --check`. The capability object passes combined-registry schema
validation and its own evidence/module/command file checks. The complete
existing registry's file-check mode still fails on unrelated missing
`docs/research/apf_audio.md`; no validator was weakened.

**PROVED: disposable manifest build and resource limits.** The final manifest
was built by calling `nfl2k5_cave_manifest.build_manifest(retail, xiso,
work_dir=Path('/tmp'), progress=print)` with the pinned retail USA XBE and
`/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso`. The normal
manifest CLI invokes the same API. Its existing TemporaryDirectory owns and
removes the disposable image on every exit path. This build took 298.264
seconds, peak RSS 1,192,240 KiB. It installed the complete owner union with a
dormant empty read table, not a wired product build with selected PLAY reads.
The two-row authored runtime was exercised separately by the instruction suite.

The final manifest has 9,012 reservations, 103 observed writer calls and 105
loaded-source fingerprints. Every recorded fingerprint still matches the final
sources; the broader discovery set contains 196 files and intentionally is
not the manifest's exported subset. The older pre-refinement scratch manifest
was not used by the final gates. The protected release manifest is unchanged;
Claude must regenerate it after protected wiring and source integration.

| Evidence | SHA-256 |
| --- | --- |
| Pinned retail XBE | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| Final dormant composed XBE | `d157f62dd7a3e80150ab26da4b832e30a1c7de4cc043be0401333d9c67f95b53` |
| `.scratch/read-option/manifest.json` | `5a270efb88992e3b5875912748b43ca7694c47c2e546fb12c01e41d3b97d502c` |
| Generated unrelocated code template | `36dcd0146cd0d8ee49afd60da482e63ec020fb02cee03ede62d1e817024859e1` |
| Paired MIN option-pack PLAY | `b54805a0f8d2013ff49907a81d41b9ca1ab517a610854ba06a73902d14fd1ccf` |
| Two-row intent table | `7832f07955ff1eec66cfbe6a58e77f780da0f261619ae0df038b1396edcd427c` |

The observed final-stack allocations are RX `0x14DC640`, file `0xB8C640`,
960 bytes, and RO `0x1507E00`, file `0xBB7E00`, 64 bytes, both aligned 16.
These are observations from the union, not hard-coded allocation addresses.
The full budget plan can place them elsewhere; relocation is tested.

Before the final real-disc build, free space was 109,207,498,752 bytes and the
source disc was 6,300,499,968 bytes. The driver required free space minus the
disc and another 100 MB to remain at least 100,000,000,000 bytes, as well as
the 40 GB hard floor. Free space after the build was 102,279,094,272 bytes.
Before writing this report, there were no remaining `nfl2k5-oracle-*` temporary
directories and no scratch XBE/disc/pack copies; scratch files totaled
4,671,360 bytes. Final logs/JSON and the source-only bundle remain below
200 MB. No test or tool loaded a whole disc or archive pack into RAM, and
all measured processes remained below 2 GB. Retail XBE/PLAY evidence reads
were bounded; archive resources were read through the existing scoped reader.
No network, game/emulator boot, GUI display, audio or push was used.

**Noah's pending witness list, adapted from memo section 9.** None is complete.
Record source and patch hashes, book/play/formation, controller/layout/context,
offensive direction, snap frame, active QB/HB node and callback, interpreter
branch bits, selected read actor and actual role/blocker, task decision and
native cache value, hold/release/receiver input frames, ball owner,
transfer/throw frame, defender position/velocity and outcome. Pair video and
trace where available. Start with ten paired snaps per condition; this does
not establish long-run CPU balance.

1. **Retail baseline.** Play all five native speed options in each linked
   formation and both directions, human keep/requested pitch and CPU QB/back.
   Establish the physical Xbox input and earliest/latest accepted frame. Pass
   requires both a controlled keep and a completed lateral to the intended
   partner. Verify ordinary pass/run controls with the patch installed.
2. **Exchange interruptions and human window.** Release before/at/after the
   observed mesh, hold continuously, release/rehold, repeat/late receiver
   presses, and switch controllers/layouts. Include a QB hit at commitment,
   blocked/ahead/behind/outside back, sideline/missed pitch and loose ball;
   compare ordinary toss and flea flicker. Require one ownership outcome,
   no duplicate ball, frozen exchange, forward lateral or post-keep flip.
   Measure whether .35 seconds actually matches the visible mesh. The prompt
   requirement cannot pass until the missing prompt is implemented.
3. **Authoring fidelity.** Compare stock clone and correctly reauthored native
   branches, mirror, slots 9/10 swap, and export/import/reload. Require matching
   partner, branches and callbacks. Include a deliberately flattened negative
   control. Recompile the runtime's paired table after every final PLAY edit;
   require refusal for stale pairs and more than two reads.
4. **Zone read.** Pair backside crash, stay/widen, scrape exchange, late slant
   and ambiguous movement with a manually controlled read defender, then AI.
   Verify the retained actor is actually the correct unblocked EDGE, both mesh
   participants meet, and opposite commitments give/keep once. Repeat odd/even
   fronts, substitutions, both directions and user takeover. A changed/missing
   slot currently defaults give or may name the wrong role; a successful live
   fallback cannot be claimed for this version.
5. **RPO.** The newer brief uses EDGE as the read key; test its crash/hold
   response and also the memo's second-level coverage/run-fit/late-commitment
   scenarios as controls. Require the intended receiver to be eligible/ready,
   default give when unavailable, no handoff after committed pass, correct
   line/penalty behavior and an actual throw. Measure the native pass delay
   and whether the mesh receiver press needs to be repeated. Include motion,
   QB styles, takeover and both directions. Passing the node-entry fixture
   does not pass this witness.
6. **Defensive responsibility.** Pair retail contain/man/zone/blitz against
   designed give, designed keep, native speed option and custom reads. Track
   dive/QB/pitch responsibility before and after commitment, abandoned targets,
   pursuit timing and coverage leakage. A lucky tackle is not a correct fit.
   Retain the memo section-8 failure measurements above before proposing a
   dedicated defense tier.
7. **Lifecycle and composition.** Audibles, no-huddle, next snap, dead ball,
   turnovers, injuries, substitutions/custom personnel, controller switching,
   save/load and repeat imports must leave ordinary passes/runs clean and
   prevent leaked decisions. Test with current throw, gun, defense, depth-role,
   spy, abilities and allocator owners. A CPU-vs-CPU half tests continuity and
   callability; larger samples are needed for decision and selection balance.

The research memo in `/home/noah/Desktop/2K5-8 Editors/`, beta-61 read-option
build report, abilities/spy runtime reports and allocator scale-out report
were the local evidence/design references. Research corpus access was read
only. No protected file, other worktree or dirty source tree was edited.
