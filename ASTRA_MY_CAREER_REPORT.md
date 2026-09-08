# MyCareer MVP and the Crib movie cut

2026-09-06. **EXPERIMENTAL / UNWITNESSED.** No Xbox boot, played game,
rendered screen, audio or console save operation was witnessed in this session.
The implementation and bounded proofs below are an integration handoff, not a
claim that the complete game experience has been accepted.

## Delivered

- `mod_editor/core/nfl2k5_my_career.py`: fixed-size signed-save preparation,
  sealed setup, bounded participation ledger, allocator owner, strict XBE
  status/apply/replay, dependent byte guards, receipts and a `python3 -m` CLI.
- `tools/nfl2k5_my_career.S`, its assembler and generated
  `nfl2k5_my_career_code.py`: original i386 handlers and relocations, with no
  runtime assembler dependency. All mutable state is in owned RW memory.
- `mod_editor/core/nfl2k5_crib_reclaim.py`: independent movie-consumer patch,
  streamed plan, transactional archive/disc shrink and full retained-resource
  verification. It does not reclaim games, furniture or the shared room.
- `mod_editor/gui/my_career_panel_qt.py`: MyCareer page with MyPlayer name, QB
  style, controller and Standard/Far choices; paired save/setup publication;
  explicit Crib plan/rebuild actions; background workers and error recovery.
- Standalone writer, native-code, Crib transaction, offscreen Qt and manifest
  tests. Both XBE gates compose both owners in both installation orders.
- `docs/mod_editor/nfl2k5_my_career_capabilities.json`: two capability objects.
  The additive WIRING.md section supplies every protected integration change.

The exact names are **MyCareer** and **MyPlayer**. The brief's contradictory
"never MyCareer" sentence was treated as a typo because its explicit naming
rule repeatedly requires that exact spelling. Both switches remain off in
Basic, Advanced and Experimental. No protected file was edited; no push was
performed. The worktree's ASTRA_BRIEF.md and `.scratch/` are excluded from the
commit/bundle.

## Decisions and actual mode flow

1. Start with a signed, existing Franchise save **at NFL Draft stage 5**. Stage
   4 is Combine and 6 is Signing in retail table `0x515140`, stride 16. This
   implementation refuses other stages instead of manufacturing an offseason.
2. Studio replaces the first eligible unassigned primary-pool QB prospect that
   is not in the free-agent list. It uses the existing roster/name/template
   writer, keeps the same 84-byte record and 720,044-byte save, and leaves the
   draft-class count and destination assignment to the native game. The three
   retail QB CAP styles supply ratings. A new output folder atomically receives
   signed `MyCareer.zip`, matching `MyCareer.json`, and a receipt. The source
   container and unrelated save members survive unchanged.
3. Build includes that setup. The old FPP row at `0x501494` becomes a native
   action named MyCareer, shows the experimental instructions, and opens the
   native Load/Save screen `0x508DF0`. It does not enter FPP's forced exhibition
   target `0x526948`. Import and load the paired save through this entry.
4. A full Franchise read is paired with the setup/checkpoint. Input stays held
   until the actual season deserializer completes at `0xC5BF7`. The native
   final-generator boundary `0x2BE946` and draft entry `0x325B90` share a guarded
   one-time injection. Later regeneration of the same slot through `0x2BE923`
   invalidates the identity instead of silently restoring MyPlayer again.
5. The normal draft/signing logic selects the destination. Runtime scans the
   existing league team lists to follow signing, release, trade and recognized
   practice reserves. One native club association remains for navigation. The
   team-control getter `0xC4D50` presents CPU ownership to draft, signing and
   weekly-management consumers; native launch and menu enumeration retain the
   career club. Front Office and Gameplan launchers and known mutating screen
   dispatches are locked. The ordinary Franchise menu explicitly exits
   MyCareer and clears its requested-entry state.
6. The match-copy helper `0xC3C60` derives the match-record pointer from the
   primary identity and native team slot, rather than a name search or the
   possession-team pointer. Controller attachment, reset, assignment, automatic
   selection, manual selection and transfer handlers keep the chosen port on
   that unique live body. Binding refreshes the game's native input-mode helper;
   the other bodies retain CPU callbacks. Input detaches on absence, inactivity,
   identity loss, duplicate identity or a malformed/cyclic body list.
7. MyCareer uses Standard/Far through `0xA5490`; the main TV-camera call at
   `0xA5947` can focus on the career body's transform. Whole-game simulation at
   `0xC7A20` refuses career-team fixtures, including when MyPlayer is benched,
   and keeps the native route for other fixtures. Lost identity/checkpoint
   state refuses simulation. There is no drive-by-drive simulation.
8. A committed career fixture with a recorded appearance earns **25 XP**.
   Bench/nonappearance weeks earn zero. A 64-entry ring and monotonic fixture
   watermark suppress duplicates, including entries already evicted from the
   ring. XP caps at 1,000,000. It is a participation ledger; it does not invent
   performance statistics, spend XP or override native progression.

## Identity, checkpoint and memory contract

MyCareer requests exactly `8192 RX / 4096 RW`, both aligned to 16 bytes. Its
existing budget-fixture rows already match these real requests. It asks for
no additional RO allocation or allocator expansion. The final template is
4,410 bytes, plus a 1,280-byte immutable setup, for **5,690 / 8,192 RX bytes**.
The remaining RX bytes are sealed `0xCC` padding. RW use reaches byte 3,311 of
4,096, including checkpoint, I/O staging and a bounded list of validated
controller pointers. The release executable initializes all RW bytes to zero.

| RW span | Purpose |
| --- | --- |
| 0..1279 | Pointer-free checkpoint, creation token, identity recipe and XP ledger |
| 1280..2559 | Checkpoint I/O staging |
| 2560..2655 | Live primary/match/body/club pointers, pending-load state, hash pair, error and filename |
| 2800..3311 | At most 128 controller pointers reached and validated during binding |

The serialized identity contains a UUID token, primary pool ordinal and a
fingerprint of immutable record/name offsets. Runtime pointers never go in the
checkpoint. College and name recipe references are root-relative, bounded and
checked against the identity before native pointer restoration. A pool slot
that no longer matches, or is regenerated, becomes lost. Retirement/compaction
may therefore end this experimental career conservatively rather than search
for a lookalike.

Checkpoints use a fixed 64-slot title journal, `U:\MyCareer00.dat` through
`U:\MyCareer3F.dat`, outside signed save subdirectories. A slot is selected by
the low six bits of one FNV-1a32 hash. Two differently seeded FNV hashes pair
the complete 720,044-byte Franchise buffer; another checksum seals the
checkpoint. These are corruption/pairing checks, **not cryptographic
authentication**. Colliding slots replace older checkpoints, so this is **at
most** 64 retained snapshots, not a guarantee of 64 recoverable saves. The
latest successful journal write is the recoverable snapshot; an older save
whose journal slot was reused refuses pairing.

The native ReadFile/WriteFile wrappers inspect only successful complete
Franchise transfers, accepting requested sizes from 720,044 through the
720,896-byte sector-aligned envelope with enough reported bytes and the ROST
and Franchise markers. They preserve the original API result and stack
contract. A file read alone holds the career in a nonplaying state until the
season-load completion hook confirms it. Requested MyCareer with a missing or
damaged journal stays detached and reports the pairing error; its initial
setup can bootstrap only its paired original save. Saving uses a write-through
1280-byte checkpoint and closes the handle. Partial or damaged journal data
cannot pass readback validation. A failed journal write does not invalidate or
counterfeit the native signed save.

The memory bound is 128 body nodes. Failure clears only controller blocks
actually reached and validated, never a guessed blanket array allocation.
The binder never uses `[0xE60280]` as MyPlayer identity. Host save input is
bounded to 16 MiB, including expanded ZIP members. No test/tool reads an entire
disc or archive pack into RAM. Archive copies, hashes and rewrites use at most
1 MiB chunks; XBE reads are separately bounded to the approximately 12 MiB
executable. Synthetic disc fixtures are below 24 MiB.

## Crib movie cut and exact retail plan

The single native MOV opener at `0x272A94` is replaced with balanced cleanup
of its two stack arguments and a zero result. The native failure path selects
state 6, whose zero-context branch pops the screen without running a MOV
destructor. The 23 resource IDs remain indexed with 2048-byte tombstones;
their payload hashes, native dispatch context and XBE section digests are
checked before mutation. Mixed or foreign states refuse.

The archive shrink uses the existing music/archive streaming writer, updates
every changed pack/file directory node, compacts physical file placement and
truncates the separate output. XDVDFS lowercases pack filenames, so A..F are
normalized when pairing them with the archive's uppercase identifiers. Every
retained outer payload, ID and length, every unrelated named file and the
patched executable are verified before publication. Shared room `4248`,
trophy index `4272` and Trophy Room CDF `4291` receive explicit hash receipts.
No VIP/profile, game, furniture or award edit is performed.

Read-only streamed plan against the pinned USA image:

| Measurement | Bytes |
| --- | ---: |
| Source image | 6,300,499,968 |
| Gross 23 movie payloads | 417,169,408 |
| Retained markers | 47,104 |
| Net archive reclaim | 417,122,304 |
| Planned disc reclaim, including removed placement gaps | **417,136,640** |
| Planned output image | 5,883,363,328 |

The planned disc saving is **397.8125 MiB**. This is a streamed retail **plan**,
not a real-disc rebuild receipt. Input SHA-256:
`7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`.
The USA XBE pin is
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
XBE-only application reports zero reclaimed disc bytes. Replaying the full
image rebuild is byte-identical and reports zero additional reclaim.

## PROVED by offline and bounded execution

- Fixed-size eligible-prospect replacement, correct class count, no forced
  destination, signed container output and atomic publication/failure cleanup.
- Strict state bounds, recipe-pointer consistency, exact installed code/hooks,
  foreign/mixed/context refusal, section seals and idempotent XBE replay.
- Actual retail pointer fixup and player-copy helper, primary-to-match identity,
  guarded injection at native draft entry and final-generation boundary, and
  invalidation on later generation of the occupied slot.
- All requested binding-survival hook ABIs, selected port 0/7, callee-saved
  registers, held-input preservation, duplicate/cycle/inactive-body detachment,
  native input-mode refresh and polling of only MyPlayer's port.
- CPU getter versus launch behavior, signing/release/trade/reserve identity,
  the installed GM dispatch locks, ordinary Franchise exit, sim refusal for
  career games, and native other-fixture dispatch/commit/replay control flow.
- Standard/Far selection and exact camera focus argument replacement.
- Once-only XP after native week navigation; bounded host ring/watermark tests;
  native checkpoint checksum/pairing, seed bootstrap, damaged/missing-pair
  refusal, pending-load hold, API forwarding and handle closure.
- All 23 movie choices execute the native failure-state route without opening
  a MOV or invoking its context destructor. Synthetic 16-pack rebuilds verify
  every retained resource, exact disc length, source preservation, replay,
  stale-plan refusal and rollback before destination replacement.
- Offscreen Qt creation, no implicit writes on source selection, setup signal,
  worker errors, control recovery and invalidation of reviewed plans.
- Manifest Recorder coverage of actual MyCareer/Crib writes and zeroed RW
  allocation; complete allocator gate union and both installation orders.

The native harness uses explicit external stubs for console file handles,
hardware input mapping/polling, body animation reset, dialogs/rendering,
full-match statistical simulation and the generator's external work in its
boundary test. Routing/commit, identity, controller and checkpoint algorithms
are executed as installed x86. Stubs do not supply the decisions being proved.

## HYPOTHESIS and known limits

- No console witness proves the U: journal path, real title permission/error
  handling, every complete-read/write route, pending asynchronous I/O, power
  loss, file enumeration or cold-save recovery. Transfers that do not expose
  a complete successful buffer to the intercepted API are unsupported by this
  experiment. The pending-load guard prevents granting input merely because
  a file read succeeded. It does not establish complete native save coverage.
- The complete franchise UI lifecycle, initial MyCareer dialog/LoadSave stack,
  all indirect GM shortcuts and CPU transaction behavior remain unwitnessed.
  The known launchers/getter paths are locked; this is not proof that every
  controller/menu/back route was inventoried or that CPU lineup choices will
  start the rookie. The CPU chooses the depth chart.
- Full on-field behavior through snaps, catches, injury/substitution, defense,
  turnovers, special teams, overtime and replays needs played acceptance.
  The bounded synthetic body list proves hook behavior, not the absence of
  another native ownership writer. Body topology outside the validated bounds
  detaches conservatively.
- Standard/Far visual framing, sideline tracking and secondary/replay cameras
  are not visually proved. Only the main TV focus call is replaced.
- XP is participation-only and has no in-game spending screen. Cross-stage
  timing, byes, playoffs, offseason rollover and long-term retirement behavior
  need a season witness. Pairing is content-based; separately edited saves
  need a matching checkpoint and are not silently migrated.
- There is no real private draft-stage acceptance save in the test contract.
  Preparation/injection proofs use a small synthetic Franchise fixture. The
  private retail XBE supplies exact code and context; missing private evidence
  or optional dependencies causes precise standalone unittest skips.
- Real-disc compaction and retail Trophy Room rendering remain unwitnessed.
  The source disk was only read. Full-size acceptance copies and the usual
  real-disc manifest generation would breach the user's free-space floor.
- Protected Build/Gameplay/shell/allowlist/closure/registry wiring and release
  manifest regeneration are explicitly handed to Claude in WIRING.md. The new
  page is not silently registered by modifying another GUI panel.

The cave gate's old manifest records a different named-allocation union.
`manifest_for_allocated_union` is a **test-only** projection: every moved span
must be wholly inside its recorded owner/kind allocation, with the same size
and alignment in the actual sealed directory. All retail reservations and
parent reservations remain. Unknown grown owners refuse. Neither the protected
JSON nor the production oracle's refusal rules are weakened or regenerated.

## Validation commands and results

The new tests and both XBE gates run as standalone unittest files, without
pytest. Final results are recorded after the final source checks:

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_my_career.py` | 7 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | 13 passed |
| `python3 tests/mod_editor/test_nfl2k5_crib_reclaim.py` | 6 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_panel.py` | 3 passed, offscreen |
| `python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | 3 passed |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 59 passed, both orders |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 71 passed, both orders |
| `python3 -m tests.mod_editor.test_nfl2k5_practice_reserves` | 9 passed, existing owner regression |
| `python3 tools/nfl2k5_my_career_assemble.py --check` | generated bytes match |
| `python3 -m mod_editor.core.nfl2k5_crib_reclaim plan <retail-xiso>` | streamed plan above |

The two capability objects pass semantic registry validation and the capability
JSON Schema; their own evidence and module commands resolve to existing files.
The complete merged registry passes the strict in-memory validator with
`check_files=False`, without editing the product registry. A global file-check
run stops on the pre-existing absent `docs/research/apf_audio.md` from another
capability. New-row file checks are run separately; that baseline absence is
not hidden or repaired by this feature. `git diff --check` passes. No Xbox emulator,
display, audio, network request or push was used.

Both XBE gate processes stay well below 2 GiB RSS; final measured values and
commit information are in the completion record below. Every synthetic
disc is owned by a TemporaryDirectory and removed on exit. There is no disc or
pack copy under `.scratch/`; only small logs, JSON and research text are
retained. The main drive's observed free space stayed above 100 GB.

## Noah's played witness list

1. Create MyPlayer from an actual draft-stage signed save, build with its setup,
   import the paired save and enter through MyCareer. Check the mode label,
   dialog, controller and both Standard/Far choices.
2. Finish the native draft and signing. Compare the draft log, primary roster
   identity, destination, years pro and class size. Run final generation before
   injection, then verify a later generator never resurrects a lost slot.
3. Play every career-team fixture. Check kickoff, snap, dropback, scramble,
   handoff, completed pass, interception, fumble, punt, PAT and overtime. Input
   stays on MyPlayer and never moves to the catcher, defender or returner.
4. Bench, injure, substitute, release, trade and put MyPlayer on reserves.
   Input detaches while absent; the CPU continues on all other bodies. Test an
   undrafted/unsigned player and a later signing. Confirm the CPU manages depth,
   contracts, practice/reserves, play selection and the other ten players.
5. Try Front Office, Gameplan, roster edit, draft-pick/manual-sign shortcuts,
   sorted lists, back paths, controller reassignment and multiple connected
   pads. Report any route that grants GM or another-body control.
6. Watch TV-camera framing, sideline movement, substitutions, replays, defense
   and special teams with both camera choices. Return through the ordinary
   Franchise menu and confirm ordinary control and save loading resume.
7. Simulate other fixtures, including repeated already-completed fixtures.
   Try to simulate the career fixture while active and benched; it must refuse.
   Confirm a whole-game result and native schedule advancement for other teams.
8. Complete a participation week, a bench week and a bye. Check the checkpoint
   ledger and repeat the completed week: participation pays 25 once; absence
   pays zero. Check transitions into playoffs and the next offseason/year.
9. Save, cold restart and reload. Check the U: journal, its pairing and the
   signed Franchise save. Try missing, corrupt, short and reused-slot journals,
   read/write failures and an invalid EXTRA signature. A bad pairing must never
   give input to a replacement player. Keep a matching save/journal backup.
10. Finish a season and test retirement or a recycled/compacted roster slot.
    Report any identity migration, repeated injection or duplicate XP.
11. Build with `crib_reclaim` independently and with MyCareer. Enter every movie
    choice and back out repeatedly; check no hang or unintended reward changes.
    Enter the Trophy Room, inspect existing trophies, earn a new trophy, save
    and reload the profile. Check shared-room rendering, games and furniture.

Keep the two options experimental and off in every preset until those played
results are recorded separately.

## Completion record

The final source passes **32 new tests, 130 XBE gate tests and 9 existing
practice-reserves regression tests**. The standalone practice-reserves command
initially stopped before collecting tests because that existing file does not
add the repository root to `sys.path`; the module command above ran all nine
successfully. No unrelated test file was changed to repair its invocation.

`/usr/bin/time` measured the final memory gate at **173.65 seconds / 293,832 KiB
peak RSS** and the final cave gate at **256.78 seconds / 472,160 KiB peak RSS**.
The native proof process peaked at 327,768 KiB. The final assembler `--check`
passed, and the explicit staged diff passed whitespace validation.

The final pre-commit space check reported **101,891,928,064 free bytes** on `/`
(101.89 GB in decimal units); `.scratch/` occupied 1,000 KiB. Full-size disc
acceptance was not started because its extra copy would violate the 100 GB
floor. All temporary synthetic images were removed before this record.

Delivery uses a direct commit on `astra/r62-my-career` with the 20 reviewed
paths named explicitly for both staging and committing. Git staging succeeded,
so the bundle fallback is unnecessary. ASTRA_BRIEF.md and `.scratch/` remain
untracked, protected files remain unchanged, and no push is performed. The
commit ID is available in the final response and the local git log.
