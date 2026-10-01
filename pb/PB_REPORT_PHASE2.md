# DESIGN: pb phase 2 handoff, all 32 modern offenses

PROVED OFFLINE: Phase 2 adds 31 team-specific books to the unchanged approved Giants pack. The league contains 4,618 authored ordinary offensive plays in 809 replaced formations. Every team has a distinct fingerprint of geometry, personnel, assignments and menus after names and team identity are excluded. The new books are generated from each team's cited staff/player profile and measured 2025 personnel baseline, not a renamed Giants pack. Sources: [manifest](league_manifest.json), [profiles](research/team_profiles.json), [scheme register](research/SCHEMES.md), [generator](build_league.py).

PROVED OFFLINE: Deliverables include the [main-only lab script](lab/pb_lab.sh), [lab stages and exact ten-call sheet](lab/README.md), [all-team Build recipe](recipes/all_teams.json), [32 diagram pages](diagrams/league.html), [32-page printable sheet](diagrams/LEAGUE_PLAY_SHEETS.pdf), [per-team catalogs](catalogs/), and [complete offline receipts](receipts/league-offline.json). The original [148-play Giants sheet](diagrams/index.html) remains available. Main approved phase 1 and explicitly authorized this expansion in the evening brief; the earlier stop gate in the phase 1 report is superseded.

## PROVED OFFLINE: validation and preservation

PROVED OFFLINE: All 32 packs pass the full pack validator and compile through the existing complete-offense compiler. Build's actual final menu checker sees all 37 books and zero problems in a read-only retail archive with in-memory replacements. The five utility books are unchanged. The pinned retail Unicorn replay executes `0xE1320`, `0xE1360` and `0xACCE0` across 1,360 formations, 3,619 pages and 10,047 menu entries covering all 8,460 play records in the 32 club books. Every formation walk terminates in the expected order, every page returns, and no formation lists any play twice. Six menu-UI calls are stubbed; this is not a game simulation.

PROVED OFFLINE: The compiler's retained-record guards check all non-ordinary play names, flags, descriptors and node bytes, plus retained formation geometry, menus, categories, defensive audibles and unowned bytes. Thus each complete-offense pack preserves FG, punt, kickoff, defense, goal-line specials, Hail Mary and clock specials semantically. Pool pointers relocate during interning. No new RPO, read option, conditional branch or option intent is present. These checks apply to the books and the supplied all-team recipe; adding a separate defensive pack would intentionally change defense.

PROVED OFFLINE: Native personnel permutations differ across clubs. The generator resolves TE1/HB1/WR roles against each stock category and remaps friendly-slot operands plus the QB's eligible read ordinals. NO, NYJ and TB have no stock 12-personnel group with an HB, so their proposed 12 share is reassigned to 11 without changing shared categories. PIT and MIN can reuse an otherwise unused stock group. The catalogs expose the actual TE1/primary slot for every play. The Giants generator and shipped pack are unchanged.

PROVED OFFLINE: The largest final node pool is 1,577 / 3,500 (SD), and the largest name pool is 8,066 / 11,088 bytes (GB). Every book stays within its original fixed resource allocation; no formation or play index is added. Source: per-team compile receipts.

DESIGN: Scheme families, widths, route-depth variants, first-read preferences and menu biases are authored football choices. Staff and player associations are sourced in [SCHEMES.md](research/SCHEMES.md); measured rates remain explicitly 2025. No 2026 charting percentages, run-concept rates, motion execution or CPU call-rate guarantees are invented. Main must verify each named player occupies the intended role on the actual roster. All gameplay remains unwitnessed.

## PROVED OFFLINE: per-team summary

PROVED OFFLINE: Forms/plays are replaced ordinary offense; pages include every retained defensive and special-teams menu page as well. Personnel counts are authored plays by 11/12/21, not real snap percentages. Every row has a passing validator, retained-semantics guard, duplicate check and native replay in the receipt. DESIGN: the family, feature role and emphasis columns describe intent; the linked research register contains each row's staff/player citations.

| Team | DESIGN scheme / featured players | PROVED OFFLINE forms / plays | PROVED OFFLINE 11 / 12 / 21 calls | DESIGN extra emphasis | PROVED OFFLINE replay pages | DESIGN diagram |
| --- | --- | ---: | ---: | --- | ---: | --- |
| ARZ | McVay/LaFleur condensed zone; Trey McBride; Marvin Harrison Jr. (TE1: Trey McBride) | 24 / 151 | 85 / 66 / 0 | TE Seam, TE Drag, Y Cross | 114 | [ARZ](diagrams/ARZ.svg) |
| ATL | Stefanski zone and play action; Bijan Robinson; Kyle Pitts Sr. (HB1: Bijan Robinson) | 22 / 137 | 65 / 60 / 12 | Outside Zone, RB Slip, PA Boot | 108 | [ATL](diagrams/ATL.svg) |
| BAL | Johnson/Payton heavy personnel blend; Derrick Henry; Mark Andrews; Lamar Jackson (TE1: Mark Andrews) | 25 / 144 | 54 / 65 / 25 | Downhill, Counter, TE Seam | 109 | [BAL](diagrams/BAL.svg) |
| BUF | Payton/Brady spread timing; James Cook III; Dalton Kincaid; Josh Allen (HB1: James Cook III) | 27 / 143 | 113 / 20 / 10 | Inside Zone, RB Slip, Levels | 118 | [BUF](diagrams/BUF.svg) |
| CAR | Canales West Coast zone; Tetairoa McMillan; Chuba Hubbard (WR1: Tetairoa McMillan) | 28 / 151 | 116 / 30 / 5 | Outside Zone, Stick, Drive | 118 | [CAR](diagrams/CAR.svg) |
| CHI | Johnson multiple gap and play action; Colston Loveland; Rome Odunze (TE1: Colston Loveland) | 24 / 149 | 95 / 54 / 0 | Counter, PA Boot, TE Seam | 115 | [CHI](diagrams/CHI.svg) |
| CIN | Taylor spread passing; Ja'Marr Chase; Tee Higgins (WR1: Ja'Marr Chase) | 27 / 156 | 108 / 43 / 5 | Dagger, Levels, Mesh | 116 | [CIN](diagrams/CIN.svg) |
| CLE | Monken vertical and gap blend; Harold Fannin Jr.; Quinshon Judkins (TE1: Harold Fannin Jr.) | 27 / 153 | 84 / 64 / 5 | TE Seam, Counter, Y Cross | 110 | [CLE](diagrams/CLE.svg) |
| DAL | Schottenheimer vertical timing; CeeDee Lamb; George Pickens (WR1: CeeDee Lamb) | 23 / 139 | 103 / 24 / 12 | Dagger, Drive, Inside Zone | 111 | [DAL](diagrams/DAL.svg) |
| DEN | Payton West Coast progression; Courtland Sutton; Bo Nix (WR1: Courtland Sutton) | 24 / 150 | 120 / 18 / 12 | Stick, Levels, Mesh | 113 | [DEN](diagrams/DEN.svg) |
| DET | Petzing gap/zone and TE matchups; Jahmyr Gibbs; Sam LaPorta (HB1: Jahmyr Gibbs) | 24 / 138 | 90 / 43 / 5 | RB Slip, Counter, TE Seam | 108 | [DET](diagrams/DET.svg) |
| GB | LaFleur wide zone and verticals; Josh Jacobs; Tucker Kraft (TE1: Tucker Kraft) | 31 / 145 | 95 / 46 / 4 | Outside Zone, TE Seam, Dagger | 122 | [GB](diagrams/GB.svg) |
| HOU | McVay/Patriots structured passing; Nico Collins; C.J. Stroud (WR1: Nico Collins) | 23 / 154 | 136 / 12 / 6 | Dagger, Levels, PA Boot | 115 | [HOU](diagrams/HOU.svg) |
| IND | Steichen vertical and zone; Jonathan Taylor; Tyler Warren (TE1: Tyler Warren) | 28 / 150 | 110 / 40 / 0 | Inside Zone, TE Seam, Y Cross | 118 | [IND](diagrams/IND.svg) |
| JAX | Coen McVay multiple; Brian Thomas Jr.; Trevor Lawrence (WR1: Brian Thomas Jr.) | 24 / 152 | 116 / 30 / 6 | Dagger, Downhill, Flood | 115 | [JAX](diagrams/JAX.svg) |
| KC | Reid West Coast spread; Travis Kelce; Rashee Rice; Patrick Mahomes (TE1: Travis Kelce) | 25 / 150 | 96 / 48 / 6 | Mesh, Stick, RB Slip | 110 | [KC](diagrams/KC.svg) |
| MIA | Shanahan/Slowik zone; De'Von Achane (HB1: De'Von Achane) | 26 / 135 | 80 / 15 / 40 | Outside Zone, RB Slip, End Around | 113 | [MIA](diagrams/MIA.svg) |
| MIN | McVay wide zone and crossers; Justin Jefferson; T.J. Hockenson (WR1: Justin Jefferson) | 28 / 140 | 100 / 30 / 10 | Y Cross, Dagger, Outside Zone | 117 | [MIN](diagrams/MIN.svg) |
| NE | Erhardt-Perkins fixed progression subset; Hunter Henry; Drake Maye (TE1: Hunter Henry) | 25 / 134 | 79 / 30 / 25 | Levels, TE Seam, Drive | 113 | [NE](diagrams/NE.svg) |
| NO | Moore vertical and quick game; Chris Olave; Tyler Shough (WR1: Chris Olave) | 24 / 147 | 147 / 0 / 0 | Levels, Dagger, RB Slip | 110 | [NO](diagrams/NO.svg) |
| NYG | Nagy/Roman TE hybrid; Isaiah Likely; Jaxson Dart (TE1: Isaiah Likely) | 26 / 148 | 48 / 90 / 10 | TE Seam, TE Drag, Y Cross | 116 | [NYG](diagrams/NYG.svg) |
| NYJ | Reich West Coast vertical blend; Garrett Wilson; Breece Hall (WR1: Garrett Wilson) | 23 / 141 | 129 / 0 / 12 | Drive, RB Slip, Dagger | 113 | [NYJ](diagrams/NYJ.svg) |
| OAK | Kubiak wide zone; Brock Bowers; Ashton Jeanty (TE1: Brock Bowers) | 25 / 135 | 85 / 50 / 0 | TE Seam, Outside Zone, TE Drag | 114 | [OAK](diagrams/OAK.svg) |
| PHI | LaFleur branch with downhill core; Saquon Barkley; DeVonta Smith (WR1: DeVonta Smith) | 24 / 146 | 98 / 48 / 0 | Downhill, Outside Zone, PA Boot | 114 | [PHI](diagrams/PHI.svg) |
| PIT | McCarthy West Coast; DK Metcalf; Pat Freiermuth (WR1: DK Metcalf) | 24 / 138 | 90 / 43 / 5 | Drive, Levels, TE Seam | 103 | [PIT](diagrams/PIT.svg) |
| SD | McDaniel wide zone and crossers; Ladd McConkey; Justin Herbert (WR1: Ladd McConkey) | 24 / 143 | 114 / 12 / 17 | Outside Zone, Y Cross, RB Slip | 105 | [SD](diagrams/SD.svg) |
| SEA | Shanahan/Fleury zone and play action; Jaxon Smith-Njigba; Sam Darnold (WR1: Jaxon Smith-Njigba) | 26 / 150 | 78 / 52 / 20 | Outside Zone, PA Boot, Drive | 114 | [SEA](diagrams/SEA.svg) |
| SF | Shanahan wide zone with fullback; Christian McCaffrey; George Kittle; Kyle Juszczyk (HB1: Christian McCaffrey) | 22 / 132 | 60 / 18 / 54 | Outside Zone, RB Slip, PA Boot | 103 | [SF](diagrams/SF.svg) |
| STL | McVay condensed downhill; Puka Nacua; Kyren Williams (WR1: Puka Nacua) | 28 / 152 | 132 / 20 / 0 | Downhill, Dagger, PA Boot | 117 | [STL](diagrams/STL.svg) |
| TB | McVay/Robinson condensed passing; Emeka Egbuka; Bucky Irving (WR1: Emeka Egbuka) | 32 / 137 | 133 / 0 / 4 | Levels, RB Slip, Dagger | 123 | [TB](diagrams/TB.svg) |
| TEN | Daboll spread progression; Cam Ward; Calvin Ridley (WR1: Calvin Ridley) | 21 / 139 | 115 / 24 / 0 | Mesh, Stick, Levels | 115 | [TEN](diagrams/TEN.svg) |
| WAS | Blough multiple spread design; Terry McLaurin; Jayden Daniels (WR1: Terry McLaurin) | 25 / 139 | 99 / 35 / 5 | Mesh, Drive, Y Cross | 109 | [WAS](diagrams/WAS.svg) |

PROVED OFFLINE: Engine aliases are ARZ=Arizona, OAK=Las Vegas, SD=Los Angeles Chargers and STL=Los Angeles Rams. No engine identity abbreviation is renamed by these packs. Menu safety and semantic preservation are measured for the entire club book, not just the representative diagram calls.

## DESIGN: Build and lab handoff

DESIGN: Main can build all 32 through the existing recipe path:

```bash
python3 '/home/noah/Desktop/2K5-8 Editors/ultimate/build_ultimate.py' \
  /home/noah/2k-worktrees/b76-u4 /media/noah/Storage/MAIN_CHOSEN_OUTPUT.xiso.iso \
  --recipe /home/noah/2k-worktrees/b76-u4/pb/recipes/all_teams.json \
  --source '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'
```

PROVED OFFLINE: The recipe lists each club's own complete-offense pack, explicitly restores BuildPlan defaults over the named preset, sets `playbook_pair=false` and `read_option_runtime=false`, and leaves optional defense/personnel/kickoff writers disabled. Synthetic Build integration confirms all 32 complete-offense packs run in the first PLAY stage and reach the final menu gate. Recipe paths use `<stack>/`, so main can integrate the bundle into another reviewed stack without editing absolute pack paths. The source fingerprints reject already-modified PLAY resources.

DESIGN: For the requested Giants smoke, use `bash pb/lab/pb_lab.sh build` in turn 1. Keep its owner process alive. In turn 2 run the printed `bash pb/lab/pb_lab.sh run SESSION` command. The continuous owner keeps the EXIT cleanup trap responsible for the disc across both turns. The build and run each acquire the shared xemu lock, with the requested CPU affinity/nice values. The run waits for any existing xemu to close before its single attempt.

PROVED OFFLINE: The original v7 file was copied exactly to `lab/v7.source.json`; only the lab copies were edited. The minimal edited recipe retains the composable defense packs and ATL gun pack, omits the option pack, and adds Giants. In-memory composition passed the real checker with 37 books and zero problems. Both supplied recipes pass plan validation. Shell syntax, Python compilation and the pure command-page/freeze protocol checks were run; neither lab stage, the ultimate disc builder nor xemu was executed. See [lab-composition.json](receipts/lab-composition.json) and [lab-static.json](receipts/lab-static.json).

DESIGN: The lab is main-operated using observed `run/cmds.txt` navigation, ten exact case macros across eight formations, and explicit pre-snap confirmations. It captures the play-call page, a snap burst, mid-play and after-play frames. The cases cover inside/outside zone, mesh, Y-cross, TE seam/drag, RB slip, end around and PA boot. Its watchdog stops after a static/capture stall or a confirmed-stage progress timeout over 60 seconds and records the reason. Timed frames are not assertions that the requested play or snap actually occurred. All unfinished cases remain incomplete. Main reviews transfers, zone blocks, route traffic, screen releases and roster roles.

DESIGN: This minimal lab uses retail players and tests the authored TE1 role; it cannot witness Isaiah Likely's identity without main's reviewed SOFTDRINK roster. No second game, retry or emulator run by Astra is authorized here. True automatic motion/jet, guaranteed duo combos and RB middle screens remain held for the same phase 1 engine-evidence reasons. Full production gameplay approval remains main's decision after live testing.

## PROVED OFFLINE: reproduction and receipts

```bash
python3 pb/build_league.py --image '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'
python3 pb/verify_league.py \
  --image '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --xbe '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe'
MPLCONFIGDIR=/tmp/pb-mpl python3 pb/diagrams/render_league.py
python3 pb/lab/check_recipe.py
python3 -m pytest -q tests/mod_editor/test_nfl2k5_modern_league.py
bash -n pb/lab/pb_lab.sh
```

PROVED OFFLINE: The new league/lab suite passes 11 tests and 5,522 subtests across two complementary selections: `10 passed, 1 deselected, 5490 subtests passed in 156.02s` and `1 passed, 10 deselected, 32 subtests passed in 1.49s`. See [league-tests-final.txt](receipts/league-tests-final.txt) and [league-receipt-tests.txt](receipts/league-receipt-tests.txt). The selected existing regression suite passes 80 tests and 7,281 subtests in 774.64 seconds: [phase2-regression.txt](receipts/phase2-regression.txt). The diagram check also passed after correcting PHI/TEN featured-player display labels; encoded packs were unchanged. The initial new suite found 407 RB Slip subtest failures caused by a test that incorrectly required four distinct QB reads for native single-target screens. All failures were the same assertion; screen mode 5 correctly uses target 5 followed by zero fields. The corrected test checks that exact native screen shape while retaining distinct-read checks for ordinary passes. The initial log is kept in [league-tests-initial.txt](receipts/league-tests-initial.txt). No play assignment changed to satisfy that test.

PROVED OFFLINE: The Jev audit tool was attempted but blocked by the session's approval policy before execution. No Jev judgment is claimed. The final report is manually checked against code and receipts; [audit status](receipts/report-audit.json) records the limitation.

## PROVED OFFLINE: delivery

PROVED OFFLINE: Phase 2 starts at `c330c6684` on `job/b76-pb`. Shared Git metadata is read-only under this session's permissions. Delivery therefore uses a pathspec commit in private `.scratch/pb.git`, with `.scratch/pb-phase2.bundle` based on `c330c6684`. The commit carries the required Astra co-author line. No push, tags, other-worktree writes, copied retail binaries or xemu run are included. The supplied lab script is for main to review and run.

PROVED OFFLINE: Workspace sizes, free NVMe space and final tests are recorded in [phase2-workspace.json](receipts/phase2-workspace.json) and [phase2-tests.json](receipts/phase2-tests.json). The research source table retains its nflverse/FTN attribution and CC-BY-SA-4.0 notice; authored recipe packs remain CC0-1.0. Main's two-turn disposable lab disc is explicitly placed on Storage, with cleanup on normal and trappable signal exits. SIGKILL/power loss cannot execute a shell trap and require main to remove any abandoned ISO.
