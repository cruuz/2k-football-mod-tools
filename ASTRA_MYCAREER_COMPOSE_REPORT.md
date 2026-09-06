| Owner | SH | RO | QB | F26 | SB | AN | GO | MC | CR | CA | MP | PS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SH screen_hooks | self | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| RO read_option_v2 | PASS | self | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| QB qb_spy_man_rush | PASS | PASS | self | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| F26 franchise_2026 | PASS | PASS | PASS | self | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| SB senior_bowl | PASS | PASS | PASS | PASS | self | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| AN animation_xbe | PASS | PASS | PASS | PASS | PASS | self | PASS | PASS | PASS | PASS | PASS | PASS |
| GO guardian_overlay | PASS | PASS | PASS | PASS | PASS | PASS | self | PASS | PASS | PASS | PASS | PASS |
| MC my_career | PASS | PASS | PASS | PASS | PASS | PASS | PASS | self | PASS | PASS | PASS | PASS |
| CR crib_reclaim | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | self | PASS | PASS | PASS |
| CA calendar | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | self | PASS | PASS |
| MP music_playlist | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | self | PASS |
| PS practice_squad_screen | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | self |

**PASS means both A -> B and B -> A install successfully, both statuses are
`applied`, both replays report zero changed bytes and preserve the entire
executable, allocator replay is unchanged, and both orders have equal SHA-256.**
The ten requested owners occupy SH through CA: **45 pairs / 90 orders**.
Adding the music playlist and native Practice Squad screen yields **66 pairs /
132 orders, all passing**. QB includes the landed man/rush implementation; RO
uses the landed v2 controls. Matrix cases use default owner settings and the
complete gate request union, with only legacy Practice Squad prerequisites
installed before the selected pair. Dormant Franchise-2026 and Senior Bowl
components retain their existing runtime limitations.

# MyCareer composition correction

2026-09-06, branch `astra/r62-mycareer-compose-fix`, base
`c2748b9a02bc23f5ac0788a5dd13a8dd61f93f89`.
**EXPERIMENTAL / UNWITNESSED.** This is offline installation, ownership and
bounded instruction evidence. Noah has not played this revision.

## PROVED: conflicts and correction

| Guard owner | Exact dependent span | Partner write | Correction |
|---|---|---|---|
| Music playlist | `0x6E390..0x6E3F3`, 99-byte native screen PUSH | MyCareer `0x6E390..0x6E39A`, 10 bytes | Require complete MyCareer status, including exact relocated hook, code, setup, zero RW and seals, before restoring just the displaced bytes for the retail hash |
| Franchise Practice | Same 99-byte native screen PUSH pin | Same MyCareer hook | Same complete installation check, retaining every remaining native byte |
| Practice Squad screen | `0x6E4E0..0x6E62A`, 330-byte event dispatcher | Playlist `0x6E4E0..0x6E4E5`, 5 bytes | Existing sealed-playlist delegation is retained; it now succeeds through the repaired playlist guard |
| Screen-pass timing hooks | `0x19C740..0x19C853`, 275-byte QB initializer | Read-option v2 `pass_init`, `0x19C849..0x19C84F` | Validate both complete owned states, then both native contexts, without recursive status calls |
| Read-option v2 | Same QB initializer guard | Screen timing `qb`, `0x19C7E9..0x19C7F0` | Symmetric validation of the exact partner and complete contexts |

An automated range comparison includes **all 26 MyCareer sites**, including
its four `.rdata` writes (the entry target at `0x50149C` was omitted from the
brief's diagnostic list). It proves there is **no direct overlap** with any
Practice Squad `GUARDS` entry or cloned `TEMPLATES` span. The failure has two
indirect paths: playlist validation, and the recently revised Franchise
Practice PUSH pin through the screen's prerequisites. Crib reclamation does
not introduce a guard conflict.

The MyCareer hook remains at its existing native PUSH entry. Its existing
assembly replays the displaced prologue and comparison before returning to
`0x6E39A`; the playlist owns the separate event dispatcher. No new hook site,
code cave, instruction bytes, runtime state, feature setting or allocation is
introduced. `nfl2k5_my_career.py`, its `.S` and generated code are unchanged.
Assembler reproduction checks verify all five affected owners' emitted code.

The screen/read-option overlap is bidirectional, so directly calling each
other's public status would recurse. Each validator now separates its own
allocation/code/settings/hook checks from native-context checks. When the
known partner hook is present, both owned states and both complete contexts
must validate. There is no bypass for arbitrary JMP bytes, unknown targets,
partially installed partners or changed native tails.

The initial required gate command returned **6 passed / 156 setup errors**;
the newly landed screen/read-option conflict masked later status failures.
The first pair run, after the playlist change alone, isolated MyCareer/Practice
Squad and screen/read-option as the remaining failures. All were corrected.
The extra unprotected core changes are necessary to satisfy complete-union
composition, not new feature work.

## Regression coverage and integration repairs

`tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` is standalone
unittest, with precise missing-retail/mismatched-USA-pin skips and a bounded
16 MiB executable read. It holds only a few executable buffers, never a disc
or archive pack. Its **77 tests pass**: 66 pair cases plus 11 focused cases.
The focused cases include all six permutations of MyCareer, playlist and
Practice Squad with a nonzero MyPlayer setup and nondefault playlist, at a
second allocation layout; Franchise Practice in both orders; every byte of
the shared detours; adjacent/native guard tails; cloned templates; correctly
formed jumps into empty allocations; reverted secondary hooks; altered code,
setup and padding with fresh allocation seals; nonzero initial RW; and
nonshared partner context corruption. Refusal tests guard the install writers
against running before rejection.

The existing gate setup checked modern naming without applying it. Both gates
now apply that already-landed owner before its status check, matching their
existing reverse-order equality assertions. Both still use the complete
`tests/nfl2k5_allocator_stack.compose` owner union and replay every owner.

The budget fixture still described read-option v1 (`960 RX / 64 RO`). It now
matches the already-landed v2 `REQUESTS` (`2048 RX / 256 RW / 88 RO`). This
changes only the planning fixture, not live requests or allocator capacity.
The complete budget plan succeeds.

The bounded manifest recorder also attempted to reserve planned grown pages
while observing seven-on-seven on a still-retail image. It now adds allocator
reservations only when grown regions actually exist. The complete recorder
proof observes the real writers and rejects unattributed changes.

## Current ownership evidence and protected handoff

The protected release manifest still contains older read-option allocation
sizes. Its strict projection correctly refuses the current union. No size,
source-fingerprint, foreign-owner or production-oracle check was relaxed.
`WIRING.md` requests Claude's normal protected manifest regeneration, and
states that no dispatcher, BuildPlan, preset, GUI, allowlist, closure or
capability change is needed for this correction.

The existing `test_nfl2k5_guardian_manifest.py` recorder generated
`.scratch/mycareer-compose/observed-xbe-manifest.json`: **9,913 reservation
spans, 90 observed writer calls and 222 current source fingerprints**. It
records the complete gate XBE, validates section digests and current source
hashes, and proves the allocator mapping. It explicitly claims no new disc or
resource build. MyCareer and screen-hooks manifest tests now support the same
`NFL2K5_CAVE_MANIFEST` evidence selection already used by both XBE gates;
source-drift and changed-allocation refusals remain tested.

The complete gate XBE SHA-256 in that independently observed evidence is
`c8e4cdb17935ccbcb41e8571a0286e0b8af8e8c76c4f117e9f8f0853e1d66ad3`.
A separate direct `stack.compose(retail)` check produces the same hash in
both orders:
`42abf44d96093ddf4777dbc94bfb62b8ae46e9d353f6844fb0383a20c0158c49`.
These are different seeds: the complete safety gates additionally include the
landed retail-section options and modern naming.

## Exact validation

All owner suites ran as separate `python3 tests/mod_editor/<file>.py`
processes. Qt used `QT_QPA_PLATFORM=offscreen`. No final test was skipped.
The manifest-dependent final runs select the observed evidence described
above. The protected default JSON will continue to refuse until regenerated.

```sh
NFL2K5_GUARDIAN_MANIFEST_OUTPUT=.scratch/mycareer-compose/observed-xbe-manifest.json \
  python3 tests/mod_editor/test_nfl2k5_guardian_manifest.py
export NFL2K5_CAVE_MANIFEST=.scratch/mycareer-compose/observed-xbe-manifest.json
python3 -m pytest tests/mod_editor/test_xbe_patch_cave_references.py tests/mod_editor/test_xbe_patch_memory_writes.py
python3 tests/mod_editor/test_xbe_patch_cave_references.py
python3 tests/mod_editor/test_xbe_patch_memory_writes.py
python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -v
```

| Check | Result | Time |
|---|---|---|
| Required pytest gate command | 162 passed | 608.66 s |
| Standalone cave-reference gate | 87 passed | 344.805 s |
| Standalone memory-write gate | 75 passed | 263.837 s |
| Standalone composition / guard regression suite | 77 passed | 407.911 s |
| Observed complete XBE manifest proof | 1 passed | 62.073 s |

The 24 owner/related standalone suites below add **240 passed tests**.
Together these cover 480 tests, with the 162 gates also repeated as standalone
unittest scripts for CI compatibility.

| Standalone file under `tests/mod_editor/` | Result |
|---|---|
| `test_nfl2k5_crib_reclaim.py` | 6 passed |
| `test_nfl2k5_franchise_practice.py` | 22 passed |
| `test_nfl2k5_franchise_practice_exit.py` | 13 passed |
| `test_nfl2k5_music_playlist.py` | 15 passed |
| `test_nfl2k5_music_playlist_contexts.py` | 7 passed |
| `test_nfl2k5_music_playlist_library.py` | 7 passed |
| `test_nfl2k5_music_playlist_manifest.py` | 2 passed |
| `test_nfl2k5_my_career.py` | 7 passed |
| `test_nfl2k5_my_career_manifest.py` | 3 passed |
| `test_nfl2k5_my_career_panel.py` | 3 passed |
| `test_nfl2k5_my_career_unicorn.py` | 13 passed |
| `test_nfl2k5_practice_reserves.py` | 9 passed |
| `test_nfl2k5_practice_squad_screen.py` | 10 passed |
| `test_nfl2k5_practice_squad_screen_unicorn.py` | 14 passed |
| `test_nfl2k5_qb_spy_man_rush.py` | 14 passed |
| `test_nfl2k5_qb_spy_runtime.py` | 13 passed |
| `test_nfl2k5_qb_spy_unicorn.py` | 16 passed |
| `test_nfl2k5_read_option_controls.py` | 15 passed |
| `test_nfl2k5_read_option_runtime.py` | 10 passed |
| `test_nfl2k5_read_option_unicorn.py` | 14 passed |
| `test_nfl2k5_screen_hooks.py` | 10 passed |
| `test_nfl2k5_screen_hooks_manifest.py` | 3 passed |
| `test_nfl2k5_screen_hooks_unicorn.py` | 10 passed |
| `test_music_playlist_project.py` | 4 passed |

Additional exact checks:

- `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json`: passed.
- `python3 tools/nfl2k5_my_career_assemble.py --check`: passed.
- `python3 tools/nfl2k5_music_playlist_assemble.py --check`: passed.
- `python3 tools/nfl2k5_practice_squad_screen_assemble.py --check`: passed.
- `python3 tools/nfl2k5_screen_hooks_assemble.py --check`: passed.
- `python3 tools/nfl2k5_read_option_runtime_assemble.py --check`: passed.
- `git diff --check`: passed.

Final logs and machine-readable pair matrix are under
`.scratch/mycareer-compose/`. Largest measured process RSS across all runs was **628,912 KiB
(614.2 MiB)**, below the 2 GiB limit; the pairwise suite used
177,372 KiB. `/usr/bin/time -v` metrics accompany the logs.
The drive had about 101 GiB free. A full temporary disc copy would breach the
100 GB free-space floor, so no real-disc build was started. Synthetic image
fixtures clean up through TemporaryDirectory; no disc or pack copy remains
under `.scratch/`, which stays below 200 MB.

## HYPOTHESIS, known gaps and Noah's witness list

Successful composition proves installation and validation, not interaction
through a played season or audible music continuity. Active MyCareer retains
its existing GM-screen restrictions, including the Practice Squad clone;
ordinary Franchise remains the mode for reserve management. Dormant owners'
existing readiness flags and all EXPERIMENTAL / UNWITNESSED labels remain.

1. Boot an opted-in build containing MyCareer, playlist and Practice Squad;
   record its request union, setup, playlist selection and XBE hash.
2. Enter MyCareer through its paired real draft-stage save, finish the native
   draft and signing, and verify input remains on MyPlayer. Check music through
   setup, draft, loading, gameplay, pause, replay, halftime and return.
3. Try Front Office, Gameplan and reserve management while MyCareer is active;
   verify its existing CPU-management restrictions. Exit through ordinary
   Franchise and verify Practice Squad opens, tabs work, Promote/Demote obey
   limits, and returning preserves the shared playlist behavior.
4. Repeat entry/exit, save, cold reload, practice, a game, a simulated fixture
   and a week transition. Check reserve identities and once-only career XP.
5. In the same build, compare screen-pass timing and authored read-option/RPO
   plays, including snap/reset, human give/keep/pass input and CPU reads. Check
   ordinary dropback passes and man/rush/zone spies for regressions.

No game boot, console emulator, visible GUI, audio playback, network access
or push was used. The original feature reports retain their broader witness
lists. Protected release manifest regeneration is the remaining integration
handoff, not a played acceptance claim.

## Delivery

The normal worktree accepted staging. Delivery uses `git add` and
`git commit -- <explicit paths>` for the 14 source/test/report/handoff paths
on `astra/r62-mycareer-compose-fix`. The brief, scratch evidence, generated game
bytes and every protected file are excluded. No push is performed. The final
commit identifier is given in the completion message.
