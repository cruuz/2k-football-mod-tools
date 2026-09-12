# Beta 66.1 H6: MyCareer creation and club ownership

Base: `9e4bc5d4`, branch `astra/b661-mycareer`. This continues the two creation
defects proved by H2. It does not identify or fix the reported Berman/SEGA
hangs in triage rows 5, 6 and 5b. These defects were found by research.

## Changes

| Source | Change | simwin66 address | Fully extended address |
|---|---|---|---|
| `tools/mycareer_mode/runtime.c:622`, `m3_sign_limit` | Read the installed Practice Squad limit at `0x3EE10C`; retain retail's actual 65-slot limit when `0xC3EE0` is native. Remove the artificial 54-player ceiling. | `0x14E297E` | `0x14E6EFE` |
| `tools/mycareer_mode/runtime.c:632`, `mode_sign` | Both signing paths use that capacity. Fresh signing repeats the check after native Franchise initialization and makes room through native `0x2BF9A0`. Refuse a zero limit or a cut that makes no progress. | `0x14E3D7B`; post-initialization limit call `0x14E3E9E`; cut `0x14E3EB9` | `0x14E82FB`; limit `0x14E841E`; cut `0x14E8439` |
| `tools/mycareer_mode/runtime.c:660` | Save the 84-byte player record before native contract and jersey setup. Check append success before removing free-agent ownership. Failure restores the record and shows the existing notice, retaining the staged player and team menu. | append `0x14E3F02`; success branch `0x14E3F09`; FA removal `0x14E3F36`; capture `0x14E3F69` | append `0x14E8482`; branch `0x14E8489`; FA removal `0x14E84B6`; capture `0x14E84E9` |
| `tools/mycareer_mode/runtime.c:331`, `mode_grown_member` | Validate the installed larger-roster owner and scan all 70 physical/overflow slots. Reject duplicate membership. | `0x14E35C9` | `0x14E7B49` |
| `tools/mycareer_mode/runtime.c:406`, `mode_create` | Accept version 2 only through that validator; check available CAP slots against overflow ownership too. | `0x14E378A` | `0x14E7D0A` |
| `tools/nfl2k5_my_career.S:129`, inline `resolve_team` | Find version-2 active and reserve membership through the same validator. The legacy non-inline binder remains byte-identical. | `0x14E1ED5` | `0x14E6455` |
| `tools/mycareer_mode/runtime.c:678`, unchanged `mode_next_fixture` | Scan the native schedule for the signed club's first unplayed fixture. Relocated by the preceding changes. | `0x14E3F83` | `0x14E8503` |

Addresses above use H2's exact composed build allocation layouts. They are
not fixed universal MyCareer addresses; the writer relocates the runtime for
each allocator union. `mod_editor/core/nfl2k5_my_career_mode.py:36` also guards the new staging
call hook. `mod_editor/core/nfl2k5_my_career_mode_code.py` was
regenerated with `python3 tools/mycareer_mode/build_runtime.py`.

The fresh player is still a free agent while append executes. Both the retail
append and the installed Practice Squad/arena append permit this: their
ownership preflight checks reserve ownership, not the free-agent list. Native
contract and jersey selection retain their original ordering and see the
pre-append club. Only successful append removes the free-agent pointer,
refreshes the club and captures the career. A failed append activates no
career and never reaches the Apartment. The native Franchise initialization
and any authorized teammate cuts precede append; this is not a whole-league
rollback of those operations.

The native append limit is proved at `0xC3EE6: cmp al,0x41`. Without Practice
Squad, a continuing undrafted player can therefore join a 54-player club as
player 55 without cutting a teammate. The existing draft regression now
asserts that result and still verifies the separate 53-player Practice Squad
case with an occupied reserve tail. The frontend refusal test now uses an
invalid count of 66 instead of treating native capacity 54 as full.

## Version-2 audit and discriminator

The version dispatch is `0x14E3845: cmp al,2` followed by the guarded-member
call at `0x14E384B` in simwin66; the extended addresses are `0x14E7DC5` and
`0x14E7DCB`. Version 2 reaches validation, not unconditional CAP admission.
The discriminator is the installed owner's validation, not arena size alone.
`mode_grown_member` requires `[0xB72808] == 0x92000`, the installed append jump,
and a nonzero result from the stable `ps_limit` entry at `0x3EE10C`.

`tools/practice_squad/runtime.c:107` rejects version 2 through its original
`reserve_count`. With the larger-roster owner installed,
`mod_editor/core/nfl2k5_roster_arena_growth.py:36` bridges that same entry to
`tools/roster_arena/runtime.c:94`. Its `reserve_count` and `integrity` in
`tools/roster_arena/storage.h` validate the team ordinal, metadata magic/count,
70-slot capacity, occupied reserve range, empty tail and overflow block CRC.
The block at root `+0x91C00` also checks its four schema words and option bits.
Tests supply a correctly migrated arena to the native owner and ordinary
Practice Squad owner; both refuse version 2. Wrong extent, CRC and version
also refuse before CAP mutation. This proves that the extent alone does not
authorize version 2.

Slots 0 through 64 remain native pointers at `team + 4*slot`. Slots 65 through
69 are 16-bit player indices at `root + 0x91C20 + team_ordinal*10`, with
`FFFF` denoting empty. The arena owner checks each reserve index against the
primary pool and verifies its checksum before MyCareer follows it. The helper
scans all slots during CAP preflight, so a supposedly available CAP record
already referenced in overflow is refused. Duplicate references to the career
player are invalid. `resolve_team` converts an active match to state 3 and a
reserve match to state 5, preserving the unique club association.

The signing path calls the same grown `ps_limit`, native cut policy and grown
append. That append inserts the active player before reserves, shifts the
reserve entries across the pointer/index boundary and reseals the block.
MyCareer does not write the overflow table. Two extra created teams remain
outside the native 32-club Franchise league, as defined by their owner.

## Match staging found by the required extended audit

The first corrected extended creation reached state 3, club 2, fixture 1,
the Apartment and Team Select. Its first match still lacked a bound player.
`tools/roster_arena/lifecycle.h:103`, `arena_stage`, copies the match records
directly, bypassing native `0xC3C60` and MyCareer's existing `copy` hook. The
series fixture therefore stopped at `tests/nfl2k5_my_career_cpu_fixture.py:50`
with "CPU trial must be the actual career fixture" and state `+2564 == 0`.
This was a further composition defect exposed by the requested audit.

`mod_editor/core/nfl2k5_my_career_mode.py:36` now guards the call at `0x617F3`
(retail `call 0x61730`). `tools/mycareer_mode/runtime.S:5`, `mode_stage`, calls
the installed staging routine, preserves its registers/flags and calls
`tools/mycareer_mode/runtime.c:350`, `mode_match_copy`, afterwards. The
wrapper is `0x14E5192` in simwin66 / `0x14E9712` extended; the validator is
`0x14E365F` / `0x14E7BDF`.

The validator checks each of the two staged 65-player arrays, verifies that
every team pointer names its corresponding copied record and matches the
primary creation identity: history/name pointers, ID, immutable appearance
bits and position. Exactly one match is required. It clears the binding on
invalid counts, mismatched array pointers, absence or duplicate identity.
This handles the grown staging owner without changing it or guessing the
copied position from an old source ordinal. No new data allocation is used.
The native regression observes zero `C3C60` calls and a missing binding before
the wrapper, then a correct binding after staging; malformed and duplicate
copies detach. The original non-inline binder still rebuilds identically.

## Proof and witness boundary

PROVED by bounded native execution:

- Fresh CAP, native Franchise initialization, signing, exactly one active
  club membership, no free-agent membership, state **3** (signed and active),
  and a real `mode_next_fixture` result for simwin66 and the fully extended
  build with migrated ROST. State 5 is reserve, not the active signed state.
- An actual Practice Squad append rejection after metadata corruption returns
  the existing "Roster is full." notice. The entire roster matches its
  pre-contract snapshot, the created player remains one free agent, staged
  ownership stays intact, career magic is zero and the team menu remains.
- Owner/extent/CRC/version refusal before CAP; refusal of a free CAP record
  aliased in overflow; sixteen native demotions/refills placing MyPlayer at
  overflow slot 68; native resolution as state 5/club 2 and native promotion
  restoring state 3/club 2 with the same career token and a real fixture.
- Retail and Practice Squad preseason/regular-season limits, invalid metadata
  refusal, byte-identical legacy binder rebuild, and current runtime rebuild.

The final H2-harness creation and series receipts are:

| Build | Team metadata / arena | Native cut and append | Final ownership | Next fixture / menu | First presented frame / kick command |
|---|---|---|---|---|---|
| simwin66 | 0 / `0x91000` | 53 active; cut target 52; append from 52 to 53 | one active membership, club 2, state 3; no FA membership | fixture 1, unplayed, includes club 2; Apartment then Team Select `0x51B908` | 8 updates / 8 completed; state 13 then 14 |
| fully extended | 2 / `0x92000` | 53 active; cut target 52; append from 52 to 53 | one active membership, club 2, state 3; no FA membership | fixture 1, unplayed, includes club 2; Apartment then Team Select `0x51B908` | 8 updates / 8 completed; state 13 then 14 |

`docs/nfl2k5_b661_transition_receipts.json` records these traces, full BuildPlan
options, production resource passes, owner allocations and XBE hashes. The
series now starts with the real fresh creation path; H2's manufactured
existing-career membership input was removed. Kick/approach is still an
explicit native command input. No completed physical match is claimed.

UNWITNESSED: Xbox/emulator boot, CAP rendering/input with real devices, the
visible club on the Apartment screen, a played next game, full asynchronous
resource/device loading, and the reported hangs. No emulator, GUI, audio,
network, disc image or retail copy was used. H2's production ROST/PLAY data
compilers run in memory; their declared scene/device service boundaries still
apply. Tests needing absent private retail evidence use `SkipTest`.

Noah must build a beta 66.1 disc, enter MyCareer, create a player, sign with a
club, see that club on the Apartment screen and choose **Play next game**.
Play the game. Repeat with **16 reserves** and **two extra created teams**
enabled and the paired migrated roster. Also check save/load and, if using
reserves, demotion and promotion. These options remain EXPERIMENTAL and off
by default. No claim about the reported hangs follows from passing these
creation checks.

## Budget and release handoff

The machine-code payload grows from 14,176 to 14,588 bytes: **412 bytes**.
The measured budget union contains 18,457 bytes including immutable menus,
leaving **2,006 bytes** before the 17-byte format tag. RX remains **20,480
bytes**. RW remains two **4,096-byte** allocations. No allocation size,
peer address, section geometry or XBE file size changes. No feature was
dropped; the byte budget is not a blocker. `tools/mycareer_mode/m3_budget.json`
contains the refreshed measurement. The settings, mode-4 and earlier Supersim
budget receipts remain historical snapshots.

**Claude: regenerate `data/nfl2k5_cave_reservations.json` after integration.**
The MyCareer writer is fingerprinted and changed. `WIRING.md` contains the
exact release manifest command. The protected manifest was not edited here.
The scratch projection retains parent reservations and observes current
MyCareer writes; it is explicitly not a release disc-build receipt. No GUI,
registry or dispatcher wiring is required. `packaging/repin.py --apply`
refreshes the provider pin and runs last before each explicit-path commit.

## Verification

All table entries below ran standalone with `PYTHONPATH=.`,
`QT_QPA_PLATFORM=offscreen`, `PYTHONHASHSEED=0`, and
`NFL2K5_CAVE_MANIFEST=.scratch/h6/final-gate-manifest.json`. The runtime tool
`validate_m3.py --manifest .scratch/h6/final-gate-manifest.json --output
.scratch/h6/<group>/validation.json <test files>` launched independent groups;
the listed per-file commands are its actual subprocess commands. The
transition suite ran directly with `--record`.

The build and manifest commands were:

```sh
python3 tools/mycareer_mode/build_runtime.py
python3 tools/mycareer_mode/build_runtime.py --check
python3 tools/nfl2k5_my_career_assemble.py --check
python3 tools/mycareer_mode/measure_m3.py --output tools/mycareer_mode/m3_budget.json
python3 tools/mycareer_mode/refresh_gate_manifest.py \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --output .scratch/h6/final-gate-manifest.json --base-revision 9e4bc5d4
python3 tools/mycareer_mode/refresh_m3_manifest.py \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --output .scratch/h6/final-m3-manifest.json
python3 tools/mycareer_mode/refresh_settings_manifest.py \
  --output .scratch/h6/final-settings-manifest.json
```

Outputs: `MyCareer mode runtime generated`, `MyCareer mode runtime verified`,
`MyCareer template verified`; the measurement wrote the budget above. The
gate projection reports 129 added retail reservations, RX 20480 and RW 8192.
The M3 projection reports 10080 spans. The settings projection reports 12854
spans and 129 observed steps. All three name exactly the two changed mode
Python writers and report `disc_built: false`. Root free space was 87 GiB,
below the required 100 GiB floor; no disc copy was made.

Final result: **40 standalone suites, 889 tests: 888 passed, one skipped,
zero failures.** The skip is the existing bounded generic-disc fixture,
which requires the 100 GB root free-space reserve. All native H6 tests
and all 659 tests in the four XBE gates ran and passed.

The exact command and final output lines for each suite follow. The full
machine-readable receipt is `docs/nfl2k5_b661_mycareer_validation.json`;
it includes source/manifest/log hashes, instruction addresses and budget.

| Command | Final output |
|---|---|
| `python3 tests/mod_editor/test_beta66_supersim_wiring.py` | `Ran 3 tests in 0.265s`<br>`OK`<br>`MAX_RSS_KIB=78684` |
| `python3 tests/mod_editor/test_nfl2k5_b661_transition.py --record` | `Ran 11 tests in 558.286s`<br>`OK` |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | `Ran 29 tests in 408.499s`<br>`OK`<br>`MAX_RSS_KIB=910576` |
| `python3 tests/mod_editor/test_nfl2k5_my_career.py` | `Ran 13 tests in 21.322s`<br>`OK`<br>`MAX_RSS_KIB=132260` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_completion.py` | `Ran 6 tests in 40.762s`<br>`OK`<br>`MAX_RSS_KIB=303072` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_control.py` | `Ran 2 tests in 18.707s`<br>`OK`<br>`MAX_RSS_KIB=238792` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_choice.py` | `Ran 1 test in 29.254s`<br>`OK`<br>`MAX_RSS_KIB=146392` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_frame.py` | `Ran 1 test in 64.730s`<br>`OK`<br>`MAX_RSS_KIB=133500` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_injury.py` | `Ran 1 test in 37.572s`<br>`OK`<br>`MAX_RSS_KIB=135348` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_period.py` | `Ran 2 tests in 47.609s`<br>`OK`<br>`MAX_RSS_KIB=169860` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_timeout.py` | `Ran 1 test in 33.786s`<br>`OK`<br>`MAX_RSS_KIB=135828` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_turnover.py` | `Ran 3 tests in 88.769s`<br>`OK`<br>`MAX_RSS_KIB=169788` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_creation_boundary.py` | `Ran 4 tests in 3.296s`<br>`OK`<br>`MAX_RSS_KIB=162676` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_draft.py` | `Ran 6 tests in 1163.562s`<br>`OK`<br>`MAX_RSS_KIB=288828` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_frontend.py` | `Ran 7 tests in 70.204s`<br>`OK`<br>`MAX_RSS_KIB=226744` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_generic_build.py` | `Ran 5 tests in 11.010s`<br>`OK (skipped=1)`<br>`MAX_RSS_KIB=162732` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_inline.py` | `Ran 8 tests in 13.527s`<br>`OK`<br>`MAX_RSS_KIB=293000` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_budget.py` | `Ran 5 tests in 4.480s`<br>`OK`<br>`MAX_RSS_KIB=126752` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_menus.py` | `Ran 4 tests in 46.800s`<br>`OK`<br>`MAX_RSS_KIB=185876` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | `Ran 3 tests in 7.977s`<br>`OK`<br>`MAX_RSS_KIB=140048` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode4.py` | `Ran 8 tests in 431.440s`<br>`OK`<br>`MAX_RSS_KIB=325752` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode5.py` | `Ran 4 tests in 279.645s`<br>`OK`<br>`MAX_RSS_KIB=434904` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_audit.py` | `Ran 6 tests in 0.065s`<br>`OK`<br>`MAX_RSS_KIB=65804` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_routes.py` | `Ran 7 tests in 2.747s`<br>`OK`<br>`MAX_RSS_KIB=325744` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_panel.py` | `Ran 4 tests in 0.177s`<br>`OK`<br>`MAX_RSS_KIB=69176` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_played.py` | `Ran 4 tests in 57.229s`<br>`OK`<br>`MAX_RSS_KIB=200276` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_position_inputs.py` | `Ran 9 tests in 17.419s`<br>`OK`<br>`MAX_RSS_KIB=309724` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_season.py` | `Ran 1 test in 149.544s`<br>`OK`<br>`MAX_RSS_KIB=193608` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_settings.py` | `Ran 9 tests in 29.505s`<br>`OK`<br>`MAX_RSS_KIB=268660` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_signing.py` | `Ran 6 tests in 62.682s`<br>`OK`<br>`MAX_RSS_KIB=369272` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | `Ran 18 tests in 11.996s`<br>`OK`<br>`MAX_RSS_KIB=298976` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_upgrades.py` | `Ran 4 tests in 250.750s`<br>`OK`<br>`MAX_RSS_KIB=370372` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_week.py` | `Ran 1 test in 323.631s`<br>`OK`<br>`MAX_RSS_KIB=168816` |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | `Ran 388 tests in 2218.047s`<br>`OK`<br>`MAX_RSS_KIB=195044` |
| `python3 tests/mod_editor/test_nfl2k5_practice_reserves.py` | `Ran 9 tests in 26.213s`<br>`OK`<br>`MAX_RSS_KIB=173892` |
| `python3 tests/mod_editor/test_nfl2k5_roster_arena_growth.py` | `Ran 13 tests in 49.918s`<br>`OK`<br>`MAX_RSS_KIB=244136` |
| `python3 tests/mod_editor/test_nfl2k5_supersim.py` | `Ran 12 tests in 8.653s`<br>`OK`<br>`MAX_RSS_KIB=264620` |
| `python3 tests/mod_editor/test_nfl2k5_supersim_live.py` | `Ran 29 tests in 3289.161s`<br>`OK`<br>`MAX_RSS_KIB=518656` |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | `Ran 127 tests in 1786.420s`<br>`OK`<br>`MAX_RSS_KIB=555264` |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | `Ran 115 tests in 1588.262s`<br>`OK`<br>`MAX_RSS_KIB=330028` |

Development probes caught the missing scene/device services before Team
Select and the grown staging bypass described above. An overflow-movement
probe needed its instruction budget raised from the fixture's 100,000 default
to 3,000,000; a test cleanup also needed a `bytes` conversion for Unicorn.
Those failed probes and suites superseded by the staging change are excluded
from the final totals. No failing final-source suite is counted as a pass.

`python3 packaging/repin.py --apply` ran last before each commit: one provider
pin for the first commit, then two for the staging fix. The final documentation
commit applies zero pin updates after all checks. The provider pins match the generated
runtime and mode writer; no protected release file was edited.

## Delivery

The supplied permission profile makes `.git` and the shared worktree Git
metadata read-only. Explicit-path commits are made with temporary metadata
under `.scratch/h6/git`, using read-only object alternates. The resulting
`ASTRA_H6.bundle` has prerequisite `9e4bc5d4`; the shared branch is untouched.
Handoff inputs, `extracted`, scratch logs and private assets are excluded.


The code commits are `3c140487` (creation, capacity and migrated ownership)
and `0d3c5a41` (binding after migrated match staging). The third commit records
the final report and successful native/release-gate receipts. After reviewing
the bundle, Claude can import the three commits from a writable integration
checkout with:

```sh
git bundle verify /path/to/ASTRA_H6.bundle
git fetch /path/to/ASTRA_H6.bundle astra/b661-mycareer
git merge --ff-only FETCH_HEAD
```

The fast-forward command assumes the destination remains at `9e4bc5d4`.
Integrate the fetched commits with the current stack if that branch has moved,
then regenerate the protected cave manifest as specified in `WIRING.md` and
repeat the release gates against that release manifest.
