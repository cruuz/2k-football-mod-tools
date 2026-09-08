# ESPN25 in-game investigation, R64

2026-09-08. Base `77d1c49f682e380b75f1a7290a806a47845608a9`.
**EXPERIMENTAL / UNWITNESSED. Builds of Historic moment rosters are blocked.**

A 12-byte native repair fixes the reproduced duplicate-Cowboys importer failure.
It passes bounded native loading, depth selection, quarterback selection, kit
lookup and roster export for all 25 moments on the actual bn executable and
resources, including return visits. This is not a completed diagnosis of both
reported gameplay failures. The reported Packers #14 and the exact loading
music wait loop were not reproduced. The brief permits refusal when the hang
cannot be fixed: the existing option applies every moment, so it now refuses
the complete option with a plain Wide Right message before copying or writing.
There is no per-moment enable switch to refuse only moment 14 safely.

## The two root-cause statements

1. **Ice Bowl #14, UNRESOLVED:** no root cause for Noah's observed Packers #14
   was established; bn's native depth builder and formation player picker choose
   Bart Starr #15 for Green Bay and Don Meredith #17 for Dallas, so the proposed
   rating-based reordering does not explain the reproduced initial state.
2. **Wide Right duplicate teams, PROVED:** `C2300` clears the active count at
   team `+11C` but leaves released player pointers at team `+0..+100`, causing
   Practice Squad's `reserve_count` to reject the next `C1030` import while
   `20CB30` ignores its failure and publishes the last successful Cowboys team
   for both sides; the subsequent loading music wait loop remains unlocated.

No statement here identifies a function as the music wait loop without evidence.
The native repair is a tested candidate, not a claim that the whole loading
freeze or #14 has been fixed.

## PROVED: execution and fields

The harness executes the user-owned native x86 instructions, without a console,
graphics, audio, network, or game session. It reads the XBE (at most 16 MiB),
main ROST 5, SITU 22, and the 35 bound historic resources through the disc's own
XDVDFS/outer descriptors. It never reads a whole pack or disc into memory.
The archive event boundary substitutes bounded resource reads; controller and
presentation callbacks retain the explicit boundaries of the prior harness.

| Stage | Native code and fields | Observation |
| --- | --- | --- |
| Main arena | `C0500`; global `B72918` | Real bn arena and relative pointer relocation |
| Scenario selection | `20CB30`, `2CFD40`, `2D1950`, `2D17B0` | Home then away descriptors and imports; 56 successful imports with repair |
| Historic import | `C1030`; bn hook to `374114`, reserve counter `3D1E9C` | Existing saved pointer order, positions and depth fields survive; edited Bills/Giants are accepted |
| Team release | `C2300`, `BFF90`; count `+11C`, 65 pointer slots at `+0..+100` | Unpatched release leaves 53 nonzero pointers with count zero; repaired release leaves none |
| Selection identity | `2D13B0`/`2D1440`, global `C8F158`; `77AE0`/`77B20`, globals `E5FE68`/`E5FE6C`; readers `77B00`/`77B40` | Unpatched Ice Bowl then Wide Right aliases both sides to `0x0200823C`, Cowboys '71 |
| Display identity | Team nickname pointer `+104`, kit code pointer `+10C`, city pointer `+138` | Read through native selected-team getters, not inferred from CSV labels |
| Match roster | `617E0`/`61730`/`C3C60`; match-team getters `61C50`/`61C60` | Independent match copies preserve all 53 player identities on each side |
| Depth initialization | `E80D0`/`E7C50`; depth getters `61C70`/`61C80` | Sorts saved rank/side chains with native availability filtering; no rating-based reorder |
| Depth fields | Player word `+28`, bits 10..12 and 13..15; availability bits at `+24` | Native rank and side insertion order agrees with the dataset's documented counts |
| Player selection | `221EE0`, `E7530`, `E75A0`, `E7810`, `E8790` and its native eligibility/dedup helpers | Translates file positions to field roles, bounds each list and resolves the quarterback; eligible starter-role reads agree with the formation picker |
| Scenario state | `10C040`/`10BD80`, native `61B80`/`61B90` player iteration, `E6680` reset and both `E7C50` rebuilds | QB and starter checks run after real late-game scalar setup; only spatial/world/clock callbacks are substituted |
| Player identity | First/last pointers `+10`/`+14`; jersey `(dword(+20) >> 3) & 127` | Fresh Ice Bowl resolves Starr 15 and Meredith 17 before and after repair |
| Kit filename | `615A0`; buffers `B30710` home / `B30730` away | Every filename in the table hashes to an existing bn outer-archive entry |
| Match export | `C0B90`, selected stadium from `77460` | Every repaired run returns a nonzero root and 106 players within a bounded buffer |

All offsets and addresses in that table are hexadecimal. Native lists are
contiguous: `E7810` trusts its caller and does not itself enforce the list's
length. The harness uses `E75A0` before reading a role ordinal, as the game does.
It translates the 17 file positions through `221EE0` and `E7530`; those enum
values cannot be passed directly as the 28 field-role values.

Fresh Ice Bowl, including real scenario setup and its depth rebuilds, with the
normal empty assigned-player set returns Starr #15 and Meredith #17. Explicitly excluding those starters through the native picker's
assigned-player argument returns Bratkowski #12 and Morton #14. That controlled
exclusion identifies the Dallas backup; it does not show that Noah's game
excluded Meredith, or that Green Bay rendered Morton. No edited Packers player
on bn wears 14. The actual actor, rendered jersey, saved substitutions and full
late-game state behind Noah's report remain outside the reproduced state.

Unpatched `select(0); match(); select(14)` gives import returns `[1, 1, 0, 0]`.
There is one native release: after that first release, the second import finds
the same apparently empty destination and rejects its stale pointer tail again.
The failure branch at `2D1896` returns without publishing a new team. Both
selection getters consequently return the previous Cowboys pointer. Directly
calling bn `reserve_count` on the released destination returns `FFFFFFFF`.

The aliased Cowboys state still produces existing `07h2.iff` and `07a2.iff`
kit names and a 106-player export in the bounded trace. This specifically
prevents treating successful kit lookup/export as proof of a resolved loading
freeze. The archive completion wait and the complete scene/renderer/sound path
were not executed. Scenario setup substitutes only `E9460`, `10BD60`,
`AF510` and the spatial callback `9CBD0`; its player reset and depth rebuilds
execute natively. There is no PROVED PC or wait-state field for the music loop.

## Repair and refusal

`nfl2k5_espn25_rosters.apply_xbe` replaces exactly four complete instructions at
`C2319` inside the existing release loop:

```text
Before: 0f b6 8e 1c 01 00 00 42 3b d1 7c ec
After:  89 04 96 42 3a 96 1c 01 00 00 72 ec
        mov [esi+edx*4], eax
        inc edx
        cmp dl, [esi+11c]
        jb C2311
```

`C2300` initializes EAX to zero, and the separately pinned `BFF90` preserves
it. The added store clears the released pointer immediately. The byte-count
comparison is equivalent for the legal maximum of 65 players. The complete
272-byte caller and nine-byte release helper are pinned, normalizing only the
12 owned bytes for applied-state recognition. Mixed, truncated or foreign code
refuses before mutation. Section digests are repinned through the existing
shared helper. Apply/status are idempotent for this executable repair.

There is no cave, new allocation, image growth, runtime data in `.text`, ratings
change, name reassignment, team identity change, main ROST edit or SITU edit.
`REQUESTS = ()`. The native differential release test compares the unmodified
team tail and player arena against the unpatched routine. The shared owner
union and manifest builder include the repair in both installation orders.

The candidate image writer preflights every resource and the executable,
rechecks them before mutation, writes fixed resource and executable spans,
flushes and verifies readback, and reports exact forward/reverse byte spans.
A complete old roster-only image is `needs load fix`, not `applied`. The
candidate can upgrade it without rewriting the installed resources. Unknown
executable bytes refuse with the bounded fixture completely unchanged. Existing
copy-first publication, handle closing, split-pack and cleanup tests also run.
This is not a two-file power-loss transaction.

`BUILD_BLOCK_REASON` is enforced by the build-facing `apply` / `apply_resources`,
`preflight_image`, `apply_to_image` and `build_image`:

> Historic moment rosters cannot be built: Wide Right has an unresolved loading
> freeze. The native team reload repair still needs gameplay verification.

The pure executable repair and private `_compile_resources` remain available
for bounded research. Writer tests explicitly clear the hold only inside their
disposable synthetic-fixture scope; production has no override argument or CLI
force switch. The actual protected BuildPlan preflight is tested to refuse the
bn-style request before copying. Full Experimental with merged positions still
refuses the existing retail-layout condition first. This session builds no new
disc for Noah. Existing bn remains byte-for-byte untouched.

`WIRING.md` records the protected dispatcher preflight update, optional native
owner tuple/kwarg, all four status surfaces, BuildPlan/presets, UI text and image
requirement, allowlist/runtime imports, and the existing capability's hold.
Those protected files were not changed. The current backend hold is effective
without that wiring; the shared GUI row/capability still need the documented
visibility/reason update. The separate saved Anniversary-plan feature is outside
this change and must not be represented as a bypass for this all-moments hold.

## All 25 moments, 50 sides on bn

This is the repaired bn native trace with retail positions and no SPECIAL rows.
Sequence: `0..24, 0, 14, 0`, one persistent main arena. All 28 selections,
56 imports and 54 releases complete; every released pointer tail is zero.
Each of the first 25 selections exports 106 players and each kit exists in bn.
The QB below is the native formation pick with no assigned players or saved
formation substitution. The team label is what the retail team object supplies,
including its original year suffix, not a corrected historical claim.

S is the number of that game's 22 documented box-score starters found in eligible
native starting-depth ordinals. All 35 chosen-file sides resolve 22/22. Across
all 50 sides the count is **903/1,100**, with **966/1,100 present**. Shared files
still prevent 15 other sides from matching their own game's complete lineup;
this investigation does not upgrade those gaps into solved starters.

| Index | Moment | Side | Native selected team | Native QB | Native kit | S |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | THE ICE BOWL | home | Packers '66 | Bart Starr #15 | `10h3.iff` | 22/22 |
| 0 | THE ICE BOWL | away | Cowboys '71 | Don Meredith #17 | `07a5.iff` | 22/22 |
| 1 | THE HEIDI BOWL | home | Raiders '67 | Daryle Lamonica #3 | `20h1.iff` | 22/22 |
| 1 | THE HEIDI BOWL | away | Jets '68 | Joe Namath #12 | `19a4.iff` | 22/22 |
| 2 | MERRY CHRISTMAS MIAMI | home | Chiefs '69 | Len Dawson #16 | `13h3.iff` | 22/22 |
| 2 | MERRY CHRISTMAS MIAMI | away | Dolphins '72 | Bob Griese #12 | `14a5.iff` | 22/22 |
| 3 | THE IMMACULATE RECEPTION | home | Steelers '75 | Terry Bradshaw #12 | `22h1.iff` | 22/22 |
| 3 | THE IMMACULATE RECEPTION | away | Raiders '67 | Daryle Lamonica #3 | `20a1.iff` | 6/22 |
| 4 | THE SEA OF HANDS | home | Raiders '76 | Ken Stabler #12 | `20h1.iff` | 22/22 |
| 4 | THE SEA OF HANDS | away | Dolphins '72 | Bob Griese #12 | `14a4.iff` | 15/22 |
| 5 | THE FINAL COMEBACK | home | Cowboys '77 | Roger Staubach #12 | `07h3.iff` | 22/22 |
| 5 | THE FINAL COMEBACK | away | Redskins '82 | Joe Theismann #7 | `29a3.iff` | 7/22 |
| 6 | THE AINTS' BIGGEST CHOKE | home | 49ers '81 | Joe Montana #16 | `25h3.iff` | 13/22 |
| 6 | THE AINTS' BIGGEST CHOKE | away | Saints '91 | Archie Manning #8 | `17a5.iff` | 22/22 |
| 7 | LONGEST PLAYOFF GAME EVER | home | Dolphins '84 | David Woodley #16 | `14h3.iff` | 22/22 |
| 7 | LONGEST PLAYOFF GAME EVER | away | Chargers '80 | Dan Fouts #14 | `24a4.iff` | 22/22 |
| 8 | THE CATCH | home | 49ers '81 | Joe Montana #16 | `25h3.iff` | 22/22 |
| 8 | THE CATCH | away | Cowboys '77 | Roger Staubach #12 | `07a2.iff` | 10/22 |
| 9 | GREATEST REDSKIN COMEBACK | home | Redskins '82 | Joe Theismann #7 | `29h2.iff` | 22/22 |
| 9 | GREATEST REDSKIN COMEBACK | away | Raiders '83 | Jim Plunkett #16 | `20a1.iff` | 22/22 |
| 10 | THE DRIVE | home | Browns '86 | Bernie Kosar #19 | `30h1.iff` | 22/22 |
| 10 | THE DRIVE | away | Broncos '86 | John Elway #7 | `08a1.iff` | 22/22 |
| 11 | THE 2-SECOND MISCALCULATION | home | Bengals '88 | Boomer Esiason #7 | `06h1.iff` | 11/22 |
| 11 | THE 2-SECOND MISCALCULATION | away | 49ers '89 | Joe Montana #16 | `25a3.iff` | 11/22 |
| 12 | SAME OLD BUCS | home | Cardinals '75 | Neil Lomax #15 | `00h3.iff` | 22/22 |
| 12 | SAME OLD BUCS | away | Buccaneers '79 | Steve DeBerg #17 | `27a3.iff` | 22/22 |
| 13 | 49ERS DO IT AGAIN | home | 49ers '89 | Joe Montana #16 | `25h3.iff` | 22/22 |
| 13 | 49ERS DO IT AGAIN | away | Bengals '88 | Boomer Esiason #7 | `06a1.iff` | 22/22 |
| 14 | WIDE RIGHT | home | Giants '90 | Jeff Hostetler #15 | `18h2.iff` | 22/22 |
| 14 | WIDE RIGHT | away | Bills '90 | Jim Kelly #12 | `03a2.iff` | 22/22 |
| 15 | HOUSTON'S HEARTS RIPPED OUT | home | Broncos '86 | John Elway #7 | `08h1.iff` | 5/22 |
| 15 | HOUSTON'S HEARTS RIPPED OUT | away | Oilers '79 | Warren Moon #1 | `28a1.iff` | 22/22 |
| 16 | THE TWO TD COMEBACK ON KC | home | Broncos '86 | John Elway #7 | `08h1.iff` | 5/22 |
| 16 | THE TWO TD COMEBACK ON KC | away | Chiefs '93 | Dave Krieg #17 | `13a2.iff` | 22/22 |
| 17 | THE BIGGEST COMEBACK EVER | home | Bills '90 | Jim Kelly #12 | `03h2.iff` | 11/22 |
| 17 | THE BIGGEST COMEBACK EVER | away | Oilers '79 | Warren Moon #1 | `28a1.iff` | 17/22 |
| 18 | THE HEARTBREAKER | home | Chiefs '93 | Dave Krieg #17 | `13h1.iff` | 7/22 |
| 18 | THE HEARTBREAKER | away | Broncos '86 | John Elway #7 | `08a1.iff` | 2/22 |
| 19 | THE COLTS' COLLAPSE | home | Bills '90 | Jim Kelly #12 | `03h2.iff` | 2/22 |
| 19 | THE COLTS' COLLAPSE | away | Colts '70 | Jim Harbaugh #4 | `11a1.iff` | 22/22 |
| 20 | THE SUPER BOWL DRIVE | home | Broncos '98 | John Elway #7 | `08h0.iff` | 22/22 |
| 20 | THE SUPER BOWL DRIVE | away | Packers '96 | Brett Favre #4 | `10a0.iff` | 22/22 |
| 21 | A YARD TOO SHORT | home | Titans '99 | Steve McNair #9 | `28h0.iff` | 22/22 |
| 21 | A YARD TOO SHORT | away | Rams '99 | Kurt Warner #13 | `23a2.iff` | 22/22 |
| 22 | VINATIERI STRIKES AGAIN | home | Patriots '01 | Tom Brady #12 | `16h0.iff` | 22/22 |
| 22 | VINATIERI STRIKES AGAIN | away | Rams '99 | Kurt Warner #13 | `23a1.iff` | 11/22 |
| 23 | THE BOTCHED SNAP | home | 49ers '03 | Jeff Garcia #5 | `25h0.iff` | 22/22 |
| 23 | THE BOTCHED SNAP | away | Giants '03 | Kerry Collins #5 | `18a0.iff` | 22/22 |
| 24 | FOURTH AND TWENTY-SIX | home | Eagles '04 | Donovan McNabb #5 | `21h0.iff` | 22/22 |
| 24 | FOURTH AND TWENTY-SIX | away | Packers '04 | Brett Favre #4 | `10a0.iff` | 22/22 |

The shared-file quarterback mismatches are explicit: index 8 away uses Roger
Staubach instead of Danny White; 17 home uses Jim Kelly instead of Frank Reich;
18 home uses Dave Krieg instead of Joe Montana; 19 home uses Jim Kelly instead
of Todd Collins. These pre-existing dataset tradeoffs are not importer
reordering and were not repaired by moving names into different rating slots.
No regeneration or network source pull was performed. The source manifest and
all 35 CSV hashes remain unchanged.

The full Experimental preset is not an allowed additional configuration:
`position_pools=True` conflicts with this option. The actual BuildPlan regression
checks that refusal. Its complete executable owner union still composes with
the repair in both XBE gates; composition is not a full-Experimental ESPN25
runtime acceptance.

## Evidence pins and limits

| Evidence | SHA-256 |
| --- | --- |
| Retail USA XBE | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| bn XBE | `f174abdc082c013ea90fa29f743c13c2810c65f6eb66d35794e28a26ad97cd52` |
| bn main ROST 5, wrapped | `996e61235f3d2e38d8b36d3aba68f9b2b20cec58ecba9b459813ec9ad0410cb2` |
| bn SITU 22, wrapped | `8a7a3742a944afbdf96da685f96a1ea5a5f3554fc2887e2ede3bd5c898ec35cc` |
| Unchanged dataset manifest | `9f2c1d1d67ef630300a081410129c71a53f9de54f4b02a89ec0cbe7087656ba8` |
| Normalized C2300, 272 bytes | `21d5e9825aff0adac9a476bbd117ada85b1fd261fd19aadab1120a2966c9b8e5` |
| BFF90, nine bytes | `4d11d20c170d21fcc60b8741c49c608e695b0885523d348d33aaad174fff714b` |

The 35 bn historic resources individually match the unchanged dataset pins.
The default bn path is the exact September 8 `bn` image named in the brief;
`NFL2K5_ESPN25_BN_IMAGE` can locate the same pinned private evidence elsewhere.
Missing Unicorn or private evidence yields a precise unittest skip. It does
not turn a skipped native trace into a pass claim. The original source pages
are absent here; their provenance tests are reported as skipped below.

Each native call is bounded at 40 million instructions, each XBE read at 16 MiB,
and each resource at the existing MAX_RESOURCE bound. The old two-million
instruction harness limit was insufficient for bn's Practice Squad import
preflight and was not evidence of a gameplay wait loop. The corrected bound
completes. The older retail harness retains its original default bound.

## Exact validation

| Exact command | Result | Peak RSS |
| --- | --- | --- |
| `ESPN25_IN_GAME_RECEIPTS=.scratch/native python3 tests/mod_editor/test_nfl2k5_espn25_in_game.py` | 7 tests, OK; 153.364 s | 229.2 MiB |
| `python3 tests/mod_editor/test_nfl2k5_espn25_rosters.py` | 23 tests, OK; one missing-source skip; 45.834 s | 180.8 MiB |
| `python3 tests/mod_editor/test_nfl2k5_espn25_rosters_native.py` | 1 tests, OK; 34.330 s | 107.5 MiB |
| `python3 tests/mod_editor/test_nfl2k5_espn25_exact_lineups.py` | 2 tests, OK; one missing-source skip; 0.087 s | not sampled |
| `python3 tests/mod_editor/test_nfl2k5_espn25_scenarios.py` | 17 tests, OK; 29.826 s | not sampled |
| `python3 tests/mod_editor/test_nfl2k5_espn25_native.py` | 7 tests, OK; 4.748 s | not sampled |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_espn25_integration_qt.py` | 13 tests, OK; 16.836 s | not sampled |
| M: `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 91 tests, OK; 804.981 s | 323.7 MiB |
| M: `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 103 tests, OK; 931.253 s | 515.0 MiB |
| M: `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 tests, OK; 203.223 s | 887.9 MiB |

`python3 -m mod_editor.core.nfl2k5_espn25_rosters validate-dataset`: OK, 35 resources, 1,855 players, 25 moments; reports the explicit build hold. `git diff --check`: OK.

The roster source check skips because the 45 private nflverse CSVs are absent. The exact-lineups private source class skips because the supplied PFR/nflverse source inputs are absent; its two dataset tests pass. No runtime native tests skipped on this machine.

All commands ran as standalone unittest scripts with ordinary Python, not
pytest. Commands marked `M` used
`NFL2K5_CAVE_MANIFEST=.scratch/espn25-in-game-manifest.json`. This is a scratch
copy of release manifest 26, current source fingerprints and the one pinned
live code span. It is not a newly observed real-disc manifest. The production
manifest remains untouched and will have its expected stale-source refusal
until Claude regenerates it. Both XBE gates enumerate the new owner in their
forward, reverse and scale-out compositions.

A final bounded receipt check also compared all 28 scenario scores, quarters
and clocks against bn SITU, and all 50 report rows against native outputs: OK.

The native run used `ESPN25_IN_GAME_RECEIPTS=.scratch/native`; derived receipts
are `failure.json` and `bn_fixed.json`. Logs and the scratch manifest remain
local. Candidate image tests use fixtures smaller than 16 MiB and temporary
directories that close and delete every handle/file. No real image or pack copy
was made, published, or retained. Root free space was about 99 GiB at final
inspection, below Noah's 100 GB preference; no disc build was attempted and no
unrelated files were removed. Scratch is under 200 MB, with no game binaries.

## HYPOTHESIS and required witness work

The stale-pointer fault may contribute to stale live identities or the later
freeze, but the native reproduction does not establish either link. Rating-
based reassignment is unsupported by the real depth and selection traces.
Graphics caching, saved substitutions, injuries/fatigue and later scene state
are unresolved possibilities, not diagnoses. Existing kits and a successful
export do not establish that the complete game load finishes.

Noah's original two observations are the only gameplay witness in this report.
The candidate has no new gameplay witness. Keep the build hold until the
remaining fault is diagnosed or a separately authorized diagnostic candidate
provides the missing evidence. For that witness:

1. Record the candidate XBE/disc recipe, selected controller side, and whether
   this is a fresh boot or a return from another moment. The original bn file
   must remain untouched.
2. Fresh Ice Bowl: compare Packers QB in pause depth, name indicator and jersey
   rendering. Expected candidate pick is Bart Starr #15; Dallas is Don Meredith
   #17. Identify the actual named player if 14 appears, including the team.
3. Finish/leave Ice Bowl without resetting, then select Wide Right. Check two
   distinct Giants/Bills names and kits, complete the loading screen, verify
   Hostetler #15 and Kelly #12, snap the ball and finish/leave the moment.
4. Repeat Ice Bowl → Wide Right → Ice Bowl and switch controller sides. Record
   any pause substitutions, injuries or automatic substitutions, plus the last
   visible loading state if a freeze occurs.
5. Run each remaining moment from the list and after another moment. Compare
   names, jerseys, eligible starters, kits, scenario state, first play, ending
   and return to menu against the 50-side table and documented shared-file
   exceptions. Include profile save/reload and a subsequent return visit.

The hold intentionally leaves no newly published image for these checks in
this session. This delivery fixes and proves one native importer defect,
refuses the unsafe all-moments build, and documents the two unresolved observed
symptoms without claiming a completed gameplay repair.


## Local delivery

Git staging on the assigned branch was available, so this delivery uses an
explicit-path commit rather than the bundle fallback. Only the feature core,
its native/fixture tests, the required owner-union and gate files, this report
and WIRING.md are included. ASTRA_BRIEF.md and .scratch are excluded. Nothing
was pushed; no other worktree or protected source file was changed.
