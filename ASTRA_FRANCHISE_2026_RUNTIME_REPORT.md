# Franchise 2026 runtime investigation, r65

2026-09-08, branch `astra/r65-franchise-2026-runtime`, base
`be99b324f34d536c625efcba7e7ea5d4f104fd2b`.
**EXPERIMENTAL / UNWITNESSED. Runtime enforcement remains blocked;
`RUNTIME_READY = False`.** The brief permits this outcome when the ownership
proofs fail. MyCareer mode 5 and the 16/17-reserve arena compose with the
Franchise-2026 owner, but neither persists its ledger or uses its game-day
selection. This revision delivers an updated read-only assessment, native
counterexamples and the exact integration handoff in the final WIRING section.
It does not claim to enforce these rules in a running game.

No console/game emulator, display, audio, network or push was used. Unicorn
ran bounded x86 instruction fixtures only. Private inputs were read-only.
The controlling rule specification remains the supplied R1-R5 snapshot;
this investigation does not introduce or refresh NFL policy.

## What changed

`mod_editor/core/nfl2k5_franchise_2026.py` now exposes
`persistence_contract()` and `save_ownership_assessment(payload)`, with a
bounded raw-save CLI, `--assess-save SAVEGAME.DAT`. It checks the existing
native container/ROST formats, overflow checksum, career footer and MyPlayer
identity, and active/reserve/IR ownership. It reports the actual auxiliary
length, reserve counts and epoch, current player-bit owners, and zero bytes
owned by a native Franchise-2026 ledger. Raw-file inspection explicitly
reports `signature_verified=False`; it does not authenticate EXTRA.

`--assess-xbe` retains all seven retail routine hashes, refuses a foreign
kernel, reports the actual kernel status and includes the current persistence
contracts. `--self-check` includes those contracts too. Its readiness error
and UI help now explain that the MyCareer block and reserve storage do not
own these counters. CLI actions are mutually exclusive. A save read is capped
at 724269 bytes and an XBE read at 12300289 bytes, rejecting an oversized input.

The capability handoff describes all four supported save sizes, modern host
reserve limits and the new proofs. It remains hidden read-only inspection
with an untested in-game status. No native code template, hook, allocator
request, save writer or host rule algorithm changed.

`tests/mod_editor/test_nfl2k5_franchise_2026_runtime.py` adds ten standalone
tests. The new development tool
`tools/franchise_2026/refresh_gate_manifest.py` supplies a conservative scratch
manifest for the stale base without copying a disc. It also verifies that
this feature's installed XBE is byte-identical to its manifest-pinned beta-62
implementation at both the minimal and complete-union allocations.

## PROVED: save ownership is still missing

| Candidate | Current ownership and counterexample |
| --- | --- |
| Player byte `+0x53` | Bit 0 is Star, bits 1-4 are abilities, bit 5 is Guardian. Mask `0x3F` is occupied; only `0xC0` remains unassigned. This corrects the brief's older statement that bits 5-7 were free. Two bits cannot hold the current four-bit/player elevation/return history, before team and IR state; this owner claims no bits. |
| MyCareer footer | `MCPL0001`, exactly 128 bytes after the complete native save. Bytes 82-83 and 88-127 must be zero. Every one of those 42 bytes is rejected by both the host and installed native validator when set and the checksum recomputed. The native encoder zeroes them. They are reserved by MyCareer, not available for borrowing. |
| Reserve arena | Arena v1 is `0x92000`, grown by 4096 bytes. Root `+0x91C00..+0x91D60` contains the 352-byte CRC-protected reserve block. It stores a pool epoch, flags and five overflow indices per team. The native auxiliary tail also remains owned; it is 366 bytes in the pinned real f0 save. Optional created-team records and their relocated objects occupy more of the growth. No part is allocated to Franchise-2026. |
| Existing signed save transport | Native containers are 720044/724140 bytes; MyCareer containers are 720172/724268 bytes. The installed admission and complete framing checks reject appended rule-ledger/companion data. Adding 4096 to a legacy save happens to equal the grown-save length, but its unmodified ROST framing is rejected; that numerical alias is not a working transport. |
| Grown XBE RW | The owner has 4096 writable runtime bytes. They are zero in a fresh XBE and have no native serialize/restore bridge. An allocator reservation is not persistent save storage. |

The reserve expansion does prove that versioned save growth can work. The
MyCareer implementation proves a signed footer can work. Neither is a shared
extension directory, nor does either grant another owner the right to change
its schema. A coordinated new format is a plausible future implementation,
not something proved impossible or something already present on this stack.

The current 4096-byte rule schema contains 512 bytes of team rows, 2048 bytes
of history nibbles and 1280 bytes of IR rows plus its header/reserved bytes.
Even ignoring optional created teams, the 4096 new arena bytes minus the
352-byte overflow and the relocated 366-byte tail leave an upper bound of
3378 bytes split across gaps. This is neither enough for the current schema
nor an ownership grant. A different compact encoding still needs lifecycle
and transport proofs. The old memo's generation-aware 60872-byte proposal
also has not been implemented by the compact host schema.

## PROVED: native save/load, staging and result boundaries

The new fixture uses a bounded synthetic 32-club franchise at regular-season
stage 8 in 2026. The first team has 53 permanent players and 17 eligible
reserves, including the five persisted overflow slots. Only the first two
clubs have players. This is a declared test setup, not a naturally played week.

All three owners are installed before execution. The existing MyCareer CPU
fixture runs native `16E540` load, all native deserializers, `16E3F0` save and
all serializers through the signing boundary. Device/authentication completion,
heap and roster-preview services remain the fixture's explicit seams. No
serializer, selector, resolver or rule decision is substituted. The existing
inline-save regression separately checks native signing and EXTRA.

For both ordinary and MyCareer grown saves, a valid ledger first holds an
accepted game and then its completed result. The two native serialized saves
are byte-identical despite the different ledger. Their native reserve rows
still contain 17 identities, their lengths remain 724140/724268, and a new
CPU instance reloads the native season and optional MyCareer identity while
the entire Franchise-2026 RW allocation stays zero. These are positive
save/load controls, not conclusions from a load that never ran.

For seven versus eight available primary C/G/T players, the host prepares
and accepts a legal selection of 47 versus 48 from 53 plus two elevations.
Both selections cover all 17 primary positions and at least two quarterbacks.
With the accepted ledger present in the actual owned RW allocation, executing
the installed `61730` staging entry reaches `arena_stage` and copies the same
53 permanent active identities. Neither elevation appears. All permanent
team bytes remain unchanged. This proves the new save owners do not connect
the rule kernel to competitive staging.

The full retail `C5280` resolver, including its native copy-list walkers,
schedule lookup and team lookup, maps normal copies back to their same-slot
owners on both sides. Replacing copy slot zero with an elevated player's
record still resolves to the permanent slot-zero player, not the elevated
identity. This extends the r62 three-instruction hazard probe to the complete
resolver and its callees. It demonstrates a concrete incorrect writeback
identity for a proposed compact projection. It does not prove every stat,
award, injury and depth consumer has been inventoried.

## Exact remaining blockers and decision

1. No Franchise-2026 save namespace or version, size admission, serialization,
   restore, signed transaction, migration and failure/retry protocol owns the
   ledger. MyCareer's fixed-length checks and the reserve arena would need a
   coordinated extension; this task forbids changing MyCareer modules.
2. No native player generation/clear/import/retirement mapping maintains rule
   history. The reserve epoch records its own lifecycle; it is not a mapping
   for elevation and IR history.
3. No competitive game-day adapter selects 47/48 from 53 plus two elevations
   and preserves permanent ownership. The existing C selector's input remains
   65 entries, while the host supports the migrated 70-player ownership limit.
4. No complete identity-aware writeback covers projected players across stats,
   injuries, awards and depth changes. C5280 remains a demonstrated blocker;
   the separately pinned 27DBC0 slot-oriented consumer is also unchanged.
5. No native elevation acceptance/cancellation/reversion, played/simulated
   completion key, IR timing/return, cutdown/trade or CPU rule event drives the
   kernel. The host companion remains an explicit digest-bound host API.

The decision is to retain `RUNTIME_READY=False`, every preset off, and the
existing pre-copy Build refusal. No new allocation, shared hook or borrowed
save byte was introduced. The owner already belongs to both XBE gate unions,
the pair matrix and the manifest builder; duplicating those entries would
not add runtime enforcement. Requests stay 5120 RX / 4096 RW, inside the
8192 RX / 4096 RW budget.

## Validation and delivery

Final commands and results are recorded in
`tools/franchise_2026/validation.json`. Each suite runs standalone with plain
`python3 tests/mod_editor/test_*.py`. Optional native fixtures have precise
retail-XBE/Unicorn skips. No whole image or archive is read into RAM.

**474 tests passed across 18 suites, with no skips in the evidence-present
runs.** Each row below uses `python3 tests/mod_editor/<file>`; the oracle,
cave-reference and allocator/owner-manifest runs use
`NFL2K5_CAVE_MANIFEST=.scratch/franchise-runtime-manifest.json`.

| Standalone file | Result | Unittest time |
| --- | --- | --- |
| `test_nfl2k5_franchise_2026.py` | 20 passed | 5.920 s |
| `test_nfl2k5_franchise_2026_unicorn.py` | 10 passed | 1.008 s |
| `test_nfl2k5_franchise_save.py` | 13 passed | 1.579 s |
| `test_nfl2k5_save_rost.py` | 9 passed | 2.664 s |
| `test_nfl2k5_roster_arena_growth.py` | 13 passed | 33.562 s |
| `test_nfl2k5_my_career_inline.py` | 8 passed | 12.975 s |
| `test_nfl2k5_allocator_scaleout.py` | 23 passed | 514.728 s |
| `test_nfl2k5_cave_oracle.py` | 28 passed | 245.817 s |
| `test_nfl2k5_my_career_manifest.py` | 3 passed | 6.704 s |
| `test_nfl2k5_guardian_manifest.py` | 1 passed | 182.860 s |
| `test_nfl2k5_music_playlist_manifest.py` | 2 passed | 3.881 s |
| `test_nfl2k5_screen_hooks_manifest.py` | 3 passed | 3.946 s |
| `test_nfl2k5_defensive_try_manifest.py` | 3 passed | 4.374 s |
| `test_nfl2k5_franchise_2026_runtime.py` | 10 passed | 69.172 s |
| `test_nfl2k5_owner_pairwise_composition.py` | 115 passed | 780.380 s |
| `test_xbe_patch_memory_writes.py` | 95 passed | 970.007 s |
| `test_xbe_patch_cave_references.py` | 107 passed | 1099.199 s |
| `test_mod_build_beta62_integration3.py` | 11 passed | 164.822 s |

The pair matrix covers 104 distinct pairs in both orders, plus the existing
screen/QB guard tests. The new suite additionally checks all six orders of
Franchise-2026, MyCareer mode 5 and arena growth. Repeating the new suite with
`NFL2K5_RETAIL_EXTRACTION=/nonexistent-franchise-evidence` gives five passed
and five explicit skipped tests in 0.981 s. The largest measured process
used 908440 KiB RSS, below the 2 GB ceiling.

The assembler `--check`, module `--self-check`, retail `--assess-xbe`, real
f0 `--assess-save`, 45-request allocation plan, scratch manifest/source-pin
validation and protected-output refusal all passed. The in-memory canonical
registry replacement passes the complete schema for 117 entries; every file
and both commands in the changed capability row resolve. The canonical
registry itself is left to Claude's integration. Twenty protected/shared
and other-owner runtime files were compared byte-for-byte to base HEAD and
remain unchanged.

The initial new suite exposed a fixture mistake: it queried slot 52 on the
second team after transferring five players away, leaving only 48 active.
The loop now derives that side's actual count and still checks both sides'
first, intermediate and last valid copies. The initial scratch projection
also needed the existing music metadata allocation before projecting the
complete union. Both corrections retain the production assertions; final
results supersede those development failures.

The owner-manifest run also exposed a base test-harness omission: the
Anniversary `XbePatch.apply` static alias retained its original writer when
the test instrumented the module. That left the actual `0xC2319` edit
(file offset `0xB2319`) unobserved. The test now routes that alias through
the same observed real writer and checks its owner reservation. No writer
output is substituted, and `Recorder.finish` still refuses every
unattributed changed byte. No Anniversary or shared recorder source changed.

The scratch manifest retains historical release reservations. All eight
changed parent fingerprints are first checked against beta-62 `77d1c49`.
The tool observes the current MyCareer, read-option diagnostic, Anniversary
repair, coverage-trail and Franchise-2026 writer calls without editing those
owners. It uses the strict gate projection for named allocations and validates
current source hashes. Its 11042 spans are for test use; inherited disc hashes
are explicitly historical. The protected release manifest is unchanged and
still requires Claude's normal regeneration after integration.

A disposable disc was not built: initial `df -h /` reported 98 GiB available,
which cannot retain the required 100 GB floor after a 6300499968-byte disc
copy. Scratch contains only bounded text/JSON/log/Git delivery artifacts and
no proprietary executable, archive, disc or save copy. Report review notes
and receipts remain under `.scratch`; the supplied brief is excluded.

Delivery uses a normal commit on the assigned branch with eight explicit
paths: this report, `WIRING.md`, the feature module and capability handoff,
the new runtime test, the Guardian manifest test correction, the scratch
manifest tool and its `validation.json` receipt. Shared Git metadata accepted
the operation, so no bundle fallback was needed. `ASTRA_BRIEF.md` and
`.scratch/` remain excluded. No push. The final response identifies the commit.

## HYPOTHESIS and Noah's future witness list

No live enforcement or completed human/CPU franchise week is claimed. After
the five blockers above are implemented and both gates pass, Noah should:

1. Play and simulate games with seven/eight OL, position coverage, special
   teams and unavailable players. Confirm exactly 47/48, correct inactives
   and both elevations from 53 permanent players, including overflow reserves.
2. Use a reserve three times in the regular season; permit the third and
   refuse the fourth, then permit postseason use after exhaustion. Exercise
   accept, cancel, retry, save/reload, inactive elevations and reversion.
3. Compare every result/injury/award/depth change to the permanent player
   identity after both played and simulated games. Repeat with MyCareer and
   the migrated reserve arena together.
4. Exercise four completed team games, byes, IR medical and roster-slot
   refusals, return budgets, both cutdown exceptions, and days 20/21 of the
   practice window. Confirm cold reload and failure/retry do not add credit.
5. Exercise season rollover, player retirement/reuse/import, signed-save
   failures and interrupted writes; retain original saves throughout.

This revision has no new playable toggle to witness. Its deliverable is the
bounded proof of the current blockers and the inspection/handoff needed to
resolve them without overwriting another feature's save state.
