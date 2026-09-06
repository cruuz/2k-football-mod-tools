# r62 franchise 2026, 2026-09-06

**EXPERIMENTAL / UNWITNESSED. The requested live franchise feature is incomplete.**
This revision delivers original host ownership transactions, an explicit counter
companion, automatic selection and a bounded native R1-R5 rule kernel. It does
not enforce these rules in a running game. `RUNTIME_READY=False`, the build
preflight raises, and the capability describes read-only inspection only. This is a
partial implementation and a concrete integration handoff, not a completed
game patch. No console or emulator session, GUI, audio, network or push occurred.

## Scope and decisions

The supplied hub memo `FRANCHISE_2026_RESEARCH_2026-09-05.md` is the frozen rule
specification. Its R1-R5 references are used below; they were not refreshed
online. Applicable prior reports, the RC85 changelog and the landed allocator,
calendar, Practice Squad, Free Practice, storage and save code informed the work.

The brief's shorthand about the third elevation conflicts with its referenced
memo. The memo explicitly permits three regular-season uses, with the third
being the last. That is the implemented rule: deny a fourth standard elevation;
do not silently perform a permanent promotion. Regular-season exhaustion does
not prevent postseason elevation. Ordinary primary-index-preserving PS moves
retain history; contract/waiver exception parity is unproved.

The brief's fallback to mapped spare record bits is not supported by the actual
memo. Its proposed ledger is `1376 + 24*N`, or **60,872 bytes at N=2479**, and it
explicitly says this does not authorize appending to retail files. The landed
storage-growth owner is an 82-byte stadium helper, not a native franchise save
extension. In the inspected player byte `+0x53`, depth/ability/star owners leave
only bits 5-7 unassigned. They cannot hold even both two-bit seasonal counters,
let alone identity generation, IR timing and pending transactions. Team cap and
statistics spans are live. No purported spare field was claimed or overwritten.

Decision: use the allotted **4,096 RW bytes** for a compact proof schema and
explicit host transport; refuse native feature activation. A host file tied to
one exact save digest cannot meet the requested native save/reload requirement.
Reducing the proposed ledger deliberately omits generation-aware native pool
lifecycle and persistent prior game-day choices; the compact schema does not
claim equivalence to the memo's full ledger.

## Delivered code and behavior

`mod_editor/core/nfl2k5_franchise_2026.py` provides:

- `RuleState`: validated, pointer-free seasonal counters and IR state, explicit
  completion keys, date advancement, rollover and host primary-pool remapping.
- `select_game_day`: deterministic 47/48 selection from up to 53 permanent
  active players and two explicit elevations from the existing 12 PS slots.
  It excludes unavailable players, covers represented primary positions and
  two QBs, supports special-role identities and valid previous choices, then
  fills by depth rank, rating and primary identity. Eight primary C/G/T players
  are required for 48. A pool below 11 available players refuses. It does not
  certify every formation's emergency substitution requirements.
- `HostSession`: candidate-copy transactions over the existing save codec and
  counters. Prepare is free; acceptance charges each elevation exactly once,
  even if inactive. Repeating acceptance after companion reload is free.
  Permanent ownership and contracts remain byte-identical for selection and
  elevation acceptance. Completion clears temporary eligibility. This is an
  explicit game-completion approximation, not the memo's first-business-day
  native reversion event.
- IR entry, four completed team games, 8 regular designations plus 2 for a
  qualifying postseason team, twice-per-player returns, two immediately charged
  cutdown exceptions, and a 21-day practice window. Byes/date-only advancement,
  preseason, stale results and exact completion retries do not add missed games.
  Expiry occurs at `start_day + 21`, exclusively: days start through start+20
  permit activation. Four missed games do not clear an injury. Activation
  requires medical clearance and an available legal 53/65 ownership slot.
- Frozen 2026 predicates for August 30 at 18:00 ET cutdown and November 10 at
  16:00 ET trade closure, including the deadline-disabled option. These are
  date predicates, not native cutdown/trade hooks or future-year calendars.
- `--self-check` and read-only `--assess-xbe PATH`, with bounded executable
  reads and pinned evidence. The assessment reports `runtime_enforced=False`.

`HostSession.prepare` uses the existing save availability/injury flags. It
does not persist prior choices, choose CPU elevations, or feed the native match
builder. The lower-level selector accepts previous choices and special-role
identities supplied by a caller; the host prepare API does not extract the
native special-role table into that selector. The kernel trusts its caller to
provide already resolved player availability, ownership and medical context.

`nfl2k5_franchise_save.py` retains the explicit Finn operation by default and
still reproduces the existing f0-to-f1 fixture exactly. The modern session
opts out of the old EE marker, preserves packed injury data and repairs the
six special-role slot indices on removal. Activation now compacts all five IR
slots, preserves non-EE packed injury data, keeps PS entries behind the active
prefix, and recomputes salary. The legacy command is an editor repair; it does
not enforce modern eligibility. Its default EE behavior remains for backwards
compatibility. Modern activation does not clear EE or medically heal a player.

The host companion is **4,168 bytes**: magic `F26HOST\x01` (8), SHA-256 of the
exact native save (32), SHA-256 of the state (32), and state (4,096). Import
checks lengths, digests, schema, season, primary pool size and matching IR
ownership. Digests detect accidental mismatch; they are not authentication.
Explicit callers remain responsible for pending-elevation ownership context.
No companion bytes are appended to `SAVEGAME.DAT`. Existing native IR entries
migrate as legacy season-ending, with no invented served games. External save
edits, including native healing/saving, invalidate the companion. Native save
load/recovery, atomic disk installation of the file pair, and automatic
companion discovery are not implemented.

## Exact counter layout

All fields are little-endian. Empty player/game identities are `0xffff`.

| Offset | Bytes | Meaning |
| --- | ---: | --- |
| 0 | 8 | `F26K`, version 1, three zero bytes |
| 8 | 8 | season u16, pool count u16 (1..4096), pool epoch u32 |
| 16 | 16 | reserved zero |
| 32 | 512 | 32 team rows, 16 bytes each |
| 544 | 2048 | one nibble/player: elevation count bits 0-1, return count bits 2-3 |
| 2592 | 1280 | 32 teams x five 8-byte IR records |
| 3872 | 224 | reserved zero |

A team row is `<HBBBBHHHHH>`: last completed game key, completed-game count,
used designations, used cutdown exceptions, postseason qualification, pending
game key, elevation A, elevation B, last day, reserved zero. An IR row is
`<HBBHH>`: primary player, completed-game ordinal at entry, flags, expiry day,
entry day. Flags are eligible=1, designation charged=2, practice=4, expired=8,
cutdown exception=16, legacy=32. Empty rows are canonical and packed.

Games are caller-supplied monotonically increasing u16 identities, not week
numbers. Counts allow at most 31 completed games/team; day numbers are 0..511.
Rollover requires the next season, empty IR and no accepted pending game, then
clears histories once. Host remapping requires a complete injective old-to-new
identity map; deleting an IR/pending identity refuses. Pool generation and
retirement adapters must supply that map; no native adapter currently does.

## Native kernel, ownership and byte evidence

Original `tools/nfl2k5_franchise_2026.c` and `.S` assemble into the checked-in
`nfl2k5_franchise_2026_code.py` template. The development assembler uses GCC,
GNU as/ld and a standard-library ELF32 relocation parser; running the feature
module does not require those tools. Rebuilding on a different compiler may
produce different bytes and must pass `--check` before updating the template.

The compiled code is **5,024 bytes**, reserved as **5,120 RX / 4,096 RW**, aligned
16, owner `nfl2k5_franchise_2026`. There is no RO allocation or borrowed cave.
The complete 34-request planned/landed budget union still fits. The game XBE
is 12,300,288 bytes after allocator scale-out. The owner has only 96 RX bytes
of reserved padding; future native hooks need a fresh budget review within
the brief's original 8,192-byte ceiling.

Kernel ECX points to its exact relocated RW workspace; EDX points to the
40-byte `<10I>` request: op, team, player, day, game key, flags, elevation A,
elevation B, active count, reserve count. Ops 0..8 are init, IR entry, game
completion, practice designation, activation, game acceptance, postseason
qualification, rollover and day advancement. Returns are 0 refusal, 1 changed,
2 replay. Input/state alias and overflow refuse. The selector takes a 640-byte
input and 104-byte output and refuses aliasing; dates use ECX=YYYYMMDD and
EDX minute/option flags. There are no calls into retail code.

`apply` installs this dormant kernel only. It validates allocator ownership,
shape, digests, sealed code and zero on-disc RW state, refuses mixed/foreign
bytes before mutation, uses `install_code` and is idempotent. Receipts state
`native_hooks=[]`, `runtime_enforced=False`, `save_growth=0`. `status=applied`
means only that the dormant kernel is installed. All listed retail consumer
spans remain untouched. `require_runtime_ready()` always rejects live use.

**PROVED by bounded retail instructions and pinned disassembly:**

- `C5280` maps a game-team slot back through permanent ownership. Executing
  its actual `C52DA` load returns permanent player 101 at slot zero when the
  proposed selected copy's slot zero is player 303. A reordered projection
  would credit the wrong player without a result identity adapter.
- `27DBC0` has a separate parallel ownership/award path. Finding one result
  consumer is insufficient to certify complete played/simulated writeback.
- The actual `2D09EC` sequence `movzx edx,ax; mov [esi],edx` destroys any
  proposed persisted upper-halfword counter in the serialized IR entry.
- `2D0F3F` restores five native slots; `2D0780` fixes the office extent.
  `247D10` and `247E20` remain retail trade predicate/pending purge paths.

Seven named span digests are recorded directly in `RUNTIME_PINS`; inspection
refuses drift. The pinned retail XBE SHA-256 is
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
These prove hazards in the inspected binary, not that every possible native
adapter has been mapped. The memo itself calls projection without verified
writeback a shipping gate.

## Verification

Every listed unittest ran standalone with plain `python3 file.py`, without
pytest or a GUI. Unicorn tests use real original kernel instructions, no
retail function stubs, a three-million-instruction ceiling, RX-only code,
write bounds, balanced stacks and callee-saved register checks. Python/native
state bytes and selection identities are compared after successful and refused
operations, including 25 deterministic shuffled selection cases.

| Command / suite | Result | Peak RSS KiB |
| --- | --- | ---: |
| `python3 tests/mod_editor/test_nfl2k5_franchise_2026.py` | 20 passed, 5.617 s | 125192 |
| `python3 tests/mod_editor/test_nfl2k5_franchise_2026_unicorn.py` | 10 passed, 0.899 s | 62032 |
| `python3 tests/mod_editor/test_nfl2k5_franchise_save.py` | 13 passed, 1.147 s | not measured |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 59 passed, 164.161 s | 270768 |
| `NFL2K5_CAVE_MANIFEST=.scratch/franchise-manifest.json python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 71 passed, 247.832 s | 481012 |
| `NFL2K5_CAVE_MANIFEST=.scratch/franchise-manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 71.221 s | 916672 |
| `python3 tools/nfl2k5_franchise_2026_assemble.py --check` | template verified | not measured |
| `python3 -m mod_editor.core.nfl2k5_franchise_2026 --self-check` | passed, runtime false | not measured |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | 34 requests fit | not measured |

The proposed capability passes structural validation after an in-memory sorted
merge, plus every new entry evidence/module/command file check. Full canonical
registry `check_files=True` is **blocked by a pre-existing missing file**,
`docs/research/apf_audio.md` in capability zero. No registry validator or existing
entry was changed to bypass that failure. The new row uses `read-only-mapped`
and hidden `view` mode for inspection; the validator requires null backend
fields for `unsafe/deferred`, which cannot describe this inspection command.

The read-only `--assess-xbe` CLI also passed against the supplied retail XBE.
An early save regression exposed changed special-role bytes in the old Finn
fixture. Restricting that repair to the explicit modern path restored the
existing exact-byte test; no fixture or assertion was weakened. Final suites
above all passed without skips in this environment.

The gate union and both gate setup assertions include this dormant owner with
all existing owners in both application orders. No safety checks or source
fingerprints were weakened. The scratch manifest is an actual experimental
disc build plus dormant-owner probe, using the existing builder against the
read-only retail disc: **9,006 spans, 103 steps**, exit zero, 4:46.92 elapsed,
peak RSS **1,164,360 KiB**. The protected production manifest was not edited.
Claude must regenerate it after integrating the final stack.

Before copying, the scratch runner required 100 GB free plus the source image
size and 1 GiB headroom (required 107,374,241,792 bytes; observed
108,912,963,584). Images lived only in the builder's `TemporaryDirectory` and
were deleted before this report; no `nfl2k5-oracle-*` directory remained. The
builder observed 105,006,747,648 bytes free afterward. Scratch contained only
small text/code/JSON evidence, approximately 2.6 MiB before the report, with
no retained game image, pack, save or executable. No whole disc/archive was
loaded into RAM; all measured processes remained below 2 GB.

## Remaining required implementation and witness list

**HYPOTHESIS / NOT IMPLEMENTED:** native saved counter allocation, serialize/
restore and wrapper integrity; complete primary-pool lifecycle; safe projection
and all stat/injury/award/depth writeback; native ownership/result retry keys;
IR event hooks, CPU return/elevation decisions and practice availability;
automatic healing integration; dated cutdown enforcement and trade acceptance/
purge guards; elevation pay; first-business-day reversion; shared native manual
screen. General IR expansion and modern PS/camp capacities remain the separate
storage migration's work. No 16/17-PS, 90/91-camp, PUP or emergency third QB
behavior is claimed. Passing kernel/gate tests does not complete these gaps.

`WIRING.md` specifies the protected BuildPlan/dispatcher/status/GUI/closure/
allowlist/capability changes. All presets stay off and true requests must refuse
before copying a disc. The schema-valid proposed capability is supplied as an
object for the canonical registry. No protected file was changed.

Noah's required witnesses, **after** the missing native integration is built:

1. **R1:** Play and simulate 53-player teams with seven versus eight OL, then
   53 plus two elevations. Confirm 47/48, correct inactive identities, depth,
   special teams and emergency substitutions. Verify a below-minimum lineup
   refuses launch and no inactive star appears. Compare all results/injuries
   to permanent identities after return to the office.
2. **R1/R2:** Accept, cancel, retry and save/reload elevations; third regular
   use works, fourth refuses, postseason still works. Verify PS contracts and
   cap/pay handling, inactive-elevation charging, cross-team reshuffling and
   first-business-day reversion, for human and CPU teams.
3. **R3/R5:** Place injured players on IR, pass a bye, preview/abort a game,
   then complete four team games through play and sim with reloads. Confirm no
   early return or duplicate credit. Start practice, attempt medical/53-slot
   refusals, activate, and compare packed injury data, PS ordering and salary.
4. **R3/R4/R5:** Exercise the eighth designation, both cutdown exceptions, the
   two qualifying postseason additions and carryover, second player return and
   refused third, day start+20 versus expiry start+21. Expired players remain
   unavailable and spending remains charged. Confirm all five native IR slots
   remain packed after a middle activation and another placement.
5. **R4:** Cross August 30 18:00 ET into the 53-player cut and August 31
   eligibility boundary. Cross November 10 16:00 ET with human, CPU and pending
   trades and deadline disabled. Preserve the existing preseason schedule.
6. **R1-R5 lifecycle:** Native save/load, legacy migration, season rollover,
   retirement/pool compaction, save failure and interrupted transactions must
   retain ownership and counters without reusing another player's history.

## Delivery

The source changes are committed with an explicit path list on
`astra/r62-franchise-2026`, based on
`b5301a7b0a9fb777d0e9de91fd89e677479975cc`. The final response identifies the
commit. `ASTRA_BRIEF.md`, `.scratch/` and all proprietary evidence are excluded.
No push. Native enforcement is explicitly unfinished.
