# ESPN 25th Anniversary exact starter lineups, r64

2026-09-08. Branch `astra/r64-espn25-exact-lineups`, base
`5704832d83672028ed0966424d5f1ec71f690661`.
**EXPERIMENTAL / UNWITNESSED. Opt-in in every preset.**

## Delivered

Extended `tools/nfl2k5_espn25_rosters_from_nflverse.py` with the offline
`nfl2k5_espn25_exact_lineups.py` evidence reader and selector. Regenerated all
35 CSVs, every CSV and applied-resource digest, and the manifest. Updated the
owner dataset pin, its shared Build/Gameplay help text, the original roster
report's Exact lineups section and per-moment table, getting started, and the
existing capability's evidence and attribution. The writer implementation is
unchanged: only names, jersey numbers and supported college indices can change.

Each chosen side reserves the box score's 22 starters before selecting 31
reserves. The remaining slots prefer the game-season PFR roster ordered by
games started, games, AV and normalized name, subject to the retail position
mix. Short or role-incomplete lists then use same-season nflverse members and
closest-season same-franchise reserves. No invented player or duplicated
identity fills a gap. The existing chosen_moment rule and every existing
manifest field survive. Fifteen losing sides explicitly list missing starters,
present starters displaced from starting depth and number mismatches.

Reproduce from the supplied local extraction, 45 nflverse CSVs and private
`.scratch/pfr/pfr_data.json`:

```sh
python3 tools/nfl2k5_espn25_rosters_from_nflverse.py --check
python3 -m mod_editor.core.nfl2k5_espn25_rosters validate-dataset
```

Use `--pfr <path>` to provide another location for the same `pfr_pull/v1`
evidence. Missing, ambiguous or incomplete starter evidence is refused.
The source pin is `6f16cd98519e69bbba7ff930f758050954388630567011034ab20bac5bdfe211`.
Current manifest pin is `9f2c1d1d67ef630300a081410129c71a53f9de54f4b02a89ec0cbe7087656ba8`.

## PROVED counts and scope

Counts of player slots are over the 35 unique files unless labeled otherwise.
The before column is the HEAD dataset. The 50-side identity/depth audit compares
normalized display names, without crediting familiar/legal-name aliases in the
older output, using the same unchanged retail slots and supplied box scores.

| Measure | Before | After |
| --- | ---: | ---: |
| Exact lineup flags, 50 sides | 0 | 35 |
| Chosen-side starters certified, 35 x 22 | 0 | 770 |
| Box-score names matched to their own PFR season page, 50 x 22 | No supplied box-score evidence | 1,100 |
| Box-score names present in loaded files, 50 sides | 937 | 966 |
| Box-score names at starting depth in loaded files, 50 sides | 431 | 903 |
| Unknown numbers, unique files | 1,173 | 123 |
| Numbers supported by the selected PFR season page | No PFR provenance | 1,732 |
| Other-season number guesses | 127 | 0 |
| Other-season roster fillers | 105 | 105 |
| Encodable college cells | 29 | 1,080 |
| Moment sides with shared-season conflicts | 15 in 12 moments | 15 in 12 moments |

The prior dataset's 555 direct nflverse-row numbers included filler seasons;
that count did not prove 555 game-season numbers. The new source pull has 2,889
rows: 50 are Team Total aggregates and never become players. The remaining
2,839 are players, 2,837 numbered. The two blank-number people are **Trey Junkin
(2002 Giants)** and **Craig Osika (2002 49ers)**. Neither fits the selected 53
under the fixed roster mix and starter priority. Thus all 123 retained unknown
numbers belong to players absent from the selected PFR season page: 105
other-season fillers and 18 additional same-season nflverse members. This is
why the remaining unknown count cannot simply be two.

Across all 50 loaded sides, including repeats and losing seasons, 2,060 of
2,650 numbers agree with a player and number on that moment's season page;
590 are unverified for that game. Side `numbers_from_game_season` and
`numbers_still_unknown` sum to 53. Existing `unknown_numbers` continues to
describe the chosen file; the new side fields describe that particular game.
Thirteen moments have both starter sets complete. E labels the box-score
evidence basis, while `exact_game_lineup_established` is false on every losing
side. No losing moment is silently called exact.

## Position and source decisions

PROVED from the retail depth table at `0x5140D8`: left WR/T/G/DE/DT/OLB/ILB/CB
roles use chain 0, the rank field; right roles use chain 1, the side field.
The first two physical records are not a universal starting pair. Explicit
left/right box positions use their chain heads. Additional unsided WR, TE or
DB starters use the next available depth for that role. A sole 1979 Cowboys
center has stored rank 1; he is still the first available center. No depth bits
or pointers are rewritten to normalize this retail anomaly.

FL/SE/E map to WR; HB/FB stay their roles and RB can use HB or FB. LDE/RDE map
to DE, LDT/RDT/NT to DT, LLB/RLB/LOLB/ROLB/SAM/WILL/SLB/WLB to OLB,
MLB/LILB/RILB to ILB, LCB/RCB to CB, and SS/FS stay their roles. Broad LB/DB/OL
bench roles stay within those families. LS in the 1968 starters table means
left safety; LS on a season roster means long snapper and can fill C.

- **The Heartbreaker, index 18:** the supplied PFR page has Kansas City away
  and Denver home; retail SITU binds Denver away and Kansas City home. Team
  names, date and roster membership prove the join; both source-side swaps are
  recorded. The retail scenario bindings are preserved.
- **SAME OLD BUCS, index 12, Lance Smith:** the raw box page itself lists SS,
  the same season roster lists RG and the box score otherwise has four
  offensive linemen. Use the roster's RG. His starter identity and number 61
  are PROVED supplied facts; the position correction is **HYPOTHESIS**, retained
  alongside the original SS label in each starter record. No hidden scrape fix.
- **Houston, index 15:** the box score has Sean Jones and Lee Williams both
  at RDE, plus William Fuller at LDE. Preserve all three identities, with Sean
  Jones and Lee Williams first and second on the right-end chain. This does
  not establish a particular defensive formation or three simultaneous DEs.
- **Jim Otto:** PFR gives `00` for Oakland. The unsigned jersey byte receives
  numeric 0, distinct from missing evidence; source text `00` remains in the
  manifest. Rendering a double zero is UNWITNESSED and outside this byte contract.
- College cells keep an encodable nflverse value; otherwise the PFR college
  fact fills the blank cell if it exactly matches one main-table string.
  Unencodable source college text remains in provenance; no new college table
  or heuristic school-name rewrite is introduced.

## Every unmatched or excluded name

**No box-score starter is unmatched to its game-season PFR roster.** All
1,100 joins use exact names in this supplied pull. Normalization and ambiguity
refusal are also implemented and tested. Familiar/legal-name joins only link
the nflverse base; PFR supplies the displayed name and season number.

The following explicit franchise-scoped aliases cover every such source join
encountered in the 50 PFR season pages. They are editorial cross-source identity
joins, not extra game-start evidence; they prevent duplicated aliases in the
reserve fallback. Will Peterson / William James is the name-change join and
is explicitly an identity interpretation. It does not supply Peterson's number.

| Team | PFR name | nflverse name |
| --- | --- | --- |
| ARZ | Pete Noga | Peter Noga |
| BUF | Marcus Spriggs | T. Marcus Spriggs |
| BUF | Rob Coons | Robert Coons |
| DEN | Bill Bryan | Billy Bryan |
| GB | Nick Luchey | Nicolas Luchey |
| IND | Bradford Banta | Brad Banta |
| KC | Dave Szott | David Szott |
| KC | Dave Whitmore | David Whitmore |
| NO | Don Schwartz | Donald Schwartz |
| NO | Mike Strachan | Michael Strachan |
| NYG | Dave Whitmore | David Whitmore |
| NYG | Will Peterson | William James |
| PHI | N.D. Kalu | Ndukwe Kalu |
| SF | Jim Robinson | Jimmy Robinson |
| SF | Mike Walter | Michael Walter |
| SF | Tom Seabron | Thomas Seabron |
| STL | Devin Bush Sr. | Devin Bush |
| STL | Mike Jones | Mike A. Jones |
| TEN | Mike Jones | Mike D. Jones |
| WAS | John McDaniel | Johnnie McDaniel |

**Bill Laskey, 1968 Oakland**, has no same-season nflverse row. His PFR row
provides name, LB position, number 42 and college; a nearby-season nflverse
identity only prevents him being added twice. This is the sole selected player
with PFR-only source-file provenance. **Nate Hobgood-Chittick, 1999 Rams**, is
excluded because `Hobgood-Chittick` has 16 characters and the existing surname
codec permits 15; no shortening or writer extension is attempted. He is not a
box-score starter. The manifest names the exact source row and reason.

All remaining number gaps are listed below by their loaded file. Each name is
a supplied nflverse player with no match on that file's selected PFR season
page. Parentheses give the nflverse season, making other-season fillers visible.
The untouched retail slot supplies an explicitly unknown jersey, with no guess
from another season.

| File; selected season | Every name without a game-season number |
| --- | --- |
| `h-03-1990-bills-2.csv`; 1990 | Brian Taylor (1991) |
| `h-06-1988-bengals-1.csv`; 1988 | Bill Johnson (1987); Curtis Jeffries (1987) |
| `h-07-1971-cowboys-4.csv`; 1967 | Dave Manders (1966); Warren Livingston (1966); Andy Stynchula (1968); Jim Colvin (1966); Obert Logan (1966); Blaine Nye (1968); A.D. Whitfield (1965); D.D. Lewis (1968); Dave Simmons (1968); Ron Widby (1968); Bill Sandeman (1966); Mike Ditka (1969) |
| `h-07-1977-cowboys-3.csv`; 1979 | Eric Hurt (1980); Dextor Clinkscale (1980); Charlie Waters (1978); Gary Hogeboom (1980); Brad Wright (1982); Jackie Smith (1978); Robert Steele (1978); Golden Richards (1978); Doug Donley (1981) |
| `h-08-1986-broncos-1.csv`; 1986 | Scott Stankavage (1986) |
| `h-10-1966-packers-3.csv`; 1967 | Gordon Rule (1968); Dave Hathcock (1966); Hank Gremminger (1965); Al Matthews (1970); Leon Crenshaw (1968); Ervin Hunt (1970); Jerry Norton (1964); Errol Mann (1968); Jesse Whittenton (1964); Dick Himes (1968); Bill Anderson (1966); Bucky Pope (1968) |
| `h-10-1996-packers-2.csv`; 1997 | Jim McMahon (1996) |
| `h-10-2004-packers-0.csv`; 2003 | Brennan Curtin (2003) |
| `h-11-1970-colts-5.csv`; 1997 | Phillip Ward (1997) |
| `h-13-1969-chiefs-4.csv`; 1971 | Jeff Kinney (1972); Jim McCann (1975); Keith Best (1972); Clyde Werner (1970); Al Palewicz (1973); Dean Carlson (1972); Larry Marshall (1972); E.J. Holub (1970); Billy Cannon (1970) |
| `h-13-1993-chiefs-2.csv`; 1992 | Mark Vlasic (1992); Matt Blundin (1992) |
| `h-14-1972-dolphins-4.csv`; 1971 | Howard Kindig (1972); Charlie Babb (1972); Maxie Williams (1970); Barry Pryor (1970); Karl Kremser (1970); Billy Lothridge (1972); Al Jenkins (1972); Marlin Briscoe (1972); Willie Richardson (1971) |
| `h-14-1984-dolphins-3.csv`; 1981 | Ralph Ortega (1980); Charles Bowser (1982); Dan Johnson (1983); Andre Tillman (1978); Mark Duper (1982) |
| `h-17-1991-saints-4.csv`; 1980 | George Rogers (1981); Hoby Brenner (1981) |
| `h-18-1990-giants-2.csv`; 1990 | Damian Johnson (1989); Clarence Jones (1991); Jay Butler (1991) |
| `h-18-2003-giants-0.csv`; 2002 | Jason Garrett (2002) |
| `h-19-1968-jets-4.csv`; 1968 | Jim Waskiewicz (1967); Bert Wilder (1967); Jim Harris (1967); Al Woodall (1969); Cecil Leonard (1969); Dave Foley (1969); Wayne Stewart (1969); Gary Arthur (1970); Harvey Nairn (1968) |
| `h-20-1967-raiders-1.csv`; 1968 | Mike Mercer (1966); Ken Herock (1967); Lloyd Edwards (1969); Drew Buie (1969) |
| `h-20-1976-raiders-0.csv`; 1974 | Charlie Phillips (1975); Jeff Queen (1973); Joe Carroll (1973); Errol Mann (1976); Willie Hall (1975); Bob Brown (1973) |
| `h-20-1983-raiders-0.csv`; 1983 | Billy Taylor (1982) |
| `h-21-2004-eagles-0.csv`; 2003 | A.J. Feeley (2003); Jeff Thomason (2002) |
| `h-22-1975-steelers-1.csv`; 1972 | Bobby Maples (1971); Dennis Meyer (1973); Bob Leahy (1971); John Brown (1972); Bob Adams (1971); Chuck Dicus (1973) |
| `h-23-1999-rams-2.csv`; 1999 | Chad Kelsay (2000) |
| `h-24-1980-chargers-4.csv`; 1981 | Booker Russell (1980); Don Woods (1980); Jim Jodat (1982); Maury Buford (1982); James Harris (1981) |
| `h-25-1989-49ers-3.csv`; 1988 | John Paye (1988) |
| `h-25-2003-49ers-0.csv`; 2002 | Garrett Johnson (2002); Brandon Doman (2002) |
| `h-28-1979-oilers-2.csv`; 1991 | Mike Rozier (1990); Erik Norgard (1991); Tony Jordan (1991); Joe Bowden (1992); Reggie Slack (1991); Bob Mrosko (1989); Chris Verhulst (1989); John Henry Mills (1993) |
| `h-28-1999-titans-0.csv`; 1999 | Kevin Daft (1999) |
| `h-29-1982-redskins-2.csv`; 1983 | Mat Mendenhall (1982); Clarence Williams (1982); Clarence Harmon (1982) |
| `h-30-1986-browns-1.csv`; 1986 | Mike Rusinek (1987); Gary Danielson (1985); Clayton Beauford (1987) |

## Every shared-file starter loss

These names are matched to their own game's evidence but absent from the
chosen shared CSV. The separate displaced list contains players present in the
file who do not occupy that game's starting role/depth. No resource is cloned.

| Moment index, side; loaded season | Absent starters | Present but displaced |
| --- | --- | --- |
| 3 away; 1968 | Marv Hubbard; Mike Siani; Raymond Chester; George Buehler; Bob Brown; Tony Cline; Otis Sistrunk; Art Thoms; Horace Jones; Phil Villapiano; Gerald Irons; Jack Tatum | Charlie Smith; Art Shell; Nemiah Wilson; George Atkinson |
| 4 away; 1971 | Benny Malone; Nat Moore | Wayne Moore; Jim Langer; Vern Den Herder; Bob Matheson; Mike Kolen |
| 5 away; 1983 | Benny Malone; Danny Buggs; Ricky Thompson; Terry Hermeling; Ron Saul; Bob Kuziel; Jeff Williams; Karl Lorch; Diron Talbert; Coy Bacon; Brad Dusek; Pete Wysocki; Lemar Parrish; Joe Lavender; Tony Peters | None |
| 6 home; 1981 | James Owens; Ron Singleton; Ray Rhodes; Charles Johnson | Lenvil Elliott; Dan Bunz; Terry Tautolo; Bobby Leopold; Ricky Churchman |
| 8 away; 1979 | Kurt Petersen; Too Tall Jones; Everson Walls; Michael Downs | Danny White; Tony Dorsett; Ron Springs; Tom Rafferty; Jim Cooper; Larry Bethea; Dennis Thurman; Charlie Waters |
| 11 away; 1988 | Joe Cribbs; Fred Quillan; Keith Fahnhorst | Mike Wilson; Ron Heller; Bubba Paris; Guy McIntyre; Randy Cross; Jeff Stover; Charles Haley; Eric Wright |
| 11 home; 1988 | Larry Kinnebrew; Dave Rimington; Robert Jackson | Cris Collinsworth; Brian Blados; Joe Walter; Eddie Edwards; Jim Skow; Emanuel King; Eric Thomas; Lewis Billups |
| 15 home; 1986 | Gaston Green; Mike Young; Derek Russell; Shannon Sharpe; Jeff Davidson; Sean Farrell; Dave Widell; Doug Widell; Mike Croel; Michael Brooks; Tyrone Braxton; Charles Dimry; Steve Atwater; Le-Lo Lang | Clarence Kay; Simon Fletcher; Karl Mecklenburg |
| 16 home; 1986 | Gaston Green; Shannon Sharpe; Reggie Johnson; Russ Freeman; Jeff Davidson; Keith Kartz; Doug Widell; Brian Sochia; Keith Traylor; Kenny Walker; Mike Croel; Tyrone Braxton; Wymon Henderson; Steve Atwater | Mark Jackson; Karl Mecklenburg; Simon Fletcher |
| 17 away; 1991 | Webster Slaughter; Eddie Robinson; Jerry Gray | Ernest Givins; Marcus Robertson |
| 17 home; 1990 | Phil Hansen; Henry Jones; Kurt Schulz | Frank Reich; Carwell Gardner; Andre Reed; Pete Metzelaars; Glenn Parker; Darryl Talley; Shane Conlan; Cliff Hicks |
| 18 away; 1986 | Leonard Russell; Cedric Tillman; Anthony Miller; Shannon Sharpe; Jerry Evans; Gary Zimmerman; Jon Melander; Dave Widell; Brian Habib; Russ Freeman; Shane Dronett; Ted Washington; Dan Williams; Mike Croel; Elijah Alexander; Ben Smith; Randy Hilliard; Steve Atwater | Simon Fletcher; Dennis Smith |
| 18 home; 1992 | Joe Montana; Marcus Allen; Derrick Walker; Will Shields; Greg Kragen; Darren Mickell; Jaime Fields; George Jamison; Mark Collins; Dave Whitmore; William White | Kimble Anders; Derrick Graham; Joe Phillips; Dale Carter |
| 19 home; 1990 | Todd Collins; Quinn Early; Lonnie Johnson; Jay Riemersma; John Fina; Ruben Brown; Jerry Ostroski; Corbin Lacina; Corey Louchiey; Phil Hansen; Ted Washington; Bryce Paup; Chris Spielman; Damien Covington; Gabe Northern; Marlon Kerner; Thomas Smith; Henry Jones; Kurt Schulz | Andre Reed |
| 22 away; 1999 | Ernie Conwell; Rod Jones; Chidi Ahanotu; Brian Young; Don Davis; Tommy Polley; Aeneas Williams; Adam Archuleta; Kim Herring | Andy McCollum; Jeff Zgonina |

The manifest additionally names every present starter whose loaded number
differs from his game's season page. All original chosen_moment, losing_moments,
uses, selector, SITU date and outer-resource identities are preserved.

## Tests and results

Final results are recorded after regeneration and the dataset pin update.
All suites run standalone with plain Python; Qt uses the offscreen platform.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_espn25_exact_lineups.py` | PASS, 6 tests |
| `python3 tests/mod_editor/test_nfl2k5_espn25_rosters.py` | PASS, 21 tests |
| `python3 tests/mod_editor/test_nfl2k5_espn25_rosters_native.py` | PASS, 1 test, all 25 moments / 2,650 player imports |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_espn25_integration_qt.py` | PASS, 13 tests |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_espn25_panel_qt.py` | PASS, 5 tests |
| `python3 tools/nfl2k5_espn25_rosters_from_nflverse.py --check` | PASS |
| `python3 -m mod_editor.core.nfl2k5_espn25_rosters validate-dataset` | PASS, 35 resources / 1,855 players / 25 moments |
| `git diff --check` | PASS |

The new test checks all 1,100 box-score identities and season numbers against
CSV rows or explicit shared-file exceptions; independent left/right chain
checks, starter-before-bench depth, GS/G/AV reserve selection, exact colleges,
source-side remapping, source anomalies, aggregate exclusion and ambiguity
refusal. Private evidence tests skip precisely when inputs are absent; all
private inputs were present here and no test was skipped.

Existing tests retain the codec, names-only import contract, ratings/appearance,
fixed spans, receipts/replay, foreign/mixed-state refusal before mutation,
transaction rollback, bounded synthetic images, closed handles and integration
checks. The final resource receipt changes **28,616 bytes**
across 35 existing resources and is saved privately as
`.scratch/exact-resource-receipt.json`. The native receipt is
`.scratch/exact-native-receipt.json`. Older shipped research receipts have their
old dataset pins and are explicitly superseded for this dataset.

## HYPOTHESIS and Noah's witness list

PROVED here means source facts, preserved bytes or bounded native x86 checks.
Noah has not played this revision. Formation choice, substitutions, injuries,
returners, long snappers, the exact eleven at the scenario's mid-game snap,
faces, equipment and double-zero rendering remain UNWITNESSED. The native test
substitutes archive I/O, controller, weather and presentation; it is not a game
boot or a game played to completion. Lance Smith's position correction and
cross-source identity aliases have the limits described above.

Build a disposable copy with **Historic moments: real rosters** selected and
the retail position layout. Open these three moments (menu numbers are index
plus one), check both pause-menu starting depth and on-field names/numbers, run
one offensive and defensive snap, and re-enter after another moment. Confirm
names remain stable, substitutions work and the scenario can finish. Expected
box-score starters below are all present at starting depth in the CSV; the
formation may use only part of this list on any one snap.

### Menu 1: THE ICE BOWL (1967-12-31)

**Away, cowboys:** Don Meredith #17 (QB); Dan Reeves #30 (HB); Don Perkins #43 (FB); Lance Rentzel #19 (FL); Bob Hayes #22 (SE); Pettis Norman #84 (TE); Tony Liscio #72 (LT); John Niland #76 (LG); Mike Connelly #53 (C); Leon Donohue #62 (RG); Ralph Neely #73 (RT); Willie Townes #71 (LDE); Jethro Pugh #75 (LDT); Bob Lilly #74 (RDT); George Andrie #66 (RDE); Chuck Howley #54 (LLB); Lee Roy Jordan #55 (MLB); Dave Edwards #52 (RLB); Cornell Green #34 (LCB); Mike Johnson #23 (RCB); Mel Renfro #20 (FS); Mike Gaechter #27 (S).

**Home, packers:** Bart Starr #15 (QB); Chuck Mercein #30 (RB); Donny Anderson #44 (HB); Carroll Dale #84 (FL); Boyd Dowler #86 (SE); Marv Fleming #81 (TE); Bob Skoronski #76 (LT); Gale Gillingham #68 (LG); Ken Bowman #57 (C); Jerry Kramer #64 (RG); Forrest Gregg #75 (RT); Willie Davis #87 (LDE); Ron Kostelnik #77 (LDT); Henry Jordan #74 (RDT); Lionel Aldridge #82 (RDE); Dave Robinson #89 (LLB); Ray Nitschke #66 (MLB); Lee Roy Caffey #60 (RLB); Herb Adderley #26 (LCB); Bob Jeter #21 (RCB); Tom Brown #40 (SS); Willie Wood #24 (FS).


### Menu 15: WIDE RIGHT (1991-01-27)

**Away, bills:** Jim Kelly #12 (QB); Thurman Thomas #34 (RB); Al Edwards #85 (WR); James Lofton #80 (WR); Andre Reed #83 (WR); Keith McKeller #84 (TE); Will Wolford #69 (LT); Jim Ritcher #51 (LG); Kent Hull #67 (C); John Davis #65 (RG); Howard Ballard #75 (RT); Leon Seals #96 (LDE); Jeff Wright #91 (NT); Bruce Smith #78 (RDE); Cornelius Bennett #97 (LOLB); Shane Conlan #58 (LILB); Ray Bentley #50 (RILB); Darryl Talley #56 (ROLB); Kirby Jackson #47 (LCB); Nate Odomes #37 (RCB); Leonard Smith #46 (SS); Mark Kelso #38 (FS).

**Home, giants:** Jeff Hostetler #15 (QB); Ottis Anderson #24 (RB); Mark Ingram #82 (WR); Mark Bavaro #89 (TE); Howard Cross #87 (TE); Bob Mrosko #80 (TE); Jumbo Elliott #76 (LT); William Roberts #66 (LG); Bart Oates #65 (C); Eric Moore #60 (RG); Doug Riesenberg #72 (RT); Erik Howard #74 (NT); Leonard Marshall #70 (RDE); Carl Banks #58 (LLB); Pepper Johnson #52 (MLB); Lawrence Taylor #56 (RLB); Mark Collins #25 (LCB); Everson Walls #28 (RCB); Greg Jackson #47 (SS); Myron Guyton #29 (FS); Reyna Thompson #21 (DB); Perry Williams #23 (DB).


### Menu 25: FOURTH AND TWENTY-SIX (2004-01-11)

**Away, packers:** Brett Favre #4 (QB); Ahman Green #30 (RB); William Henderson #33 (FB); Donald Driver #80 (WR); Robert Ferguson #89 (WR); Bubba Franks #88 (TE); Chad Clifton #76 (LT); Mike Wahle #68 (LG); Mike Flanagan #58 (C); Marco Rivera #62 (RG); Mark Tauscher #65 (RT); Aaron Kampman #74 (LDE); Cletidus Hunt #97 (DT); Grady Jackson #75 (NT); Kabeer Gbaja-Biamila #94 (RDE); Hannibal Navies #50 (SLB); Nick Barnett #56 (MLB); Na'il Diggs #59 (WLB); Mike McKenzie #34 (LCB); Al Harris #31 (RCB); Marques Anderson #20 (SS); Darren Sharper #42 (FS).

**Home, eagles:** Donovan McNabb #5 (QB); Duce Staley #22 (RB); Jon Ritchie #48 (FB); Todd Pinkston #87 (WR); James Thrash #80 (WR); Chad Lewis #89 (TE); Tra Thomas #72 (LT); John Welbourn #76 (LG); Hank Fraley #63 (C); Bobbie Williams #66 (RG); Jon Runyan #69 (RT); Brandon Whiting #98 (LDE); Corey Simon #90 (LDT); Darwin Walker #97 (RDT); N.D. Kalu #94 (RDE); Nate Wayne #54 (WILL); Mark Simoneau #53 (MLB); Ike Reese #58 (SAM); Sheldon Brown #24 (LCB); Bobby Taylor #21 (RCB); Michael Lewis #32 (SS); Brian Dawkins #20 (FS).

## Resource discipline and integration handoff

No network, game/console emulator, GUI display, audio, real-disc build, source
mutation or push. Only bounded retail entries were read, never a whole disc
or archive pack in RAM. Source free space was 101 GiB; no acceptance disc or
pack copy was retained. Test fixtures and regeneration checks use cleaned
TemporaryDirectory paths. Scratch contains private supplied PFR pages plus
small logs, scripts and receipts, below 200 MB. Final measured process memory
is recorded in the delivery results below and stays below 2 GiB.

The existing owner has no executable requests. No allocator, XBE gate owner,
position codec or runtime importer changed. No protected file was edited.
`WIRING.md` requests only the new public report's allowlist entry and reminds
the integrator to regenerate the protected cave manifest once for the stack.
The brief identifies stale reservation-source pins as inherited; they were
not refreshed or bypassed here. Runtime Build/Gameplay text already imports
this owner's HELP_TEXT, and the feature is already wired with all presets off.

The commit uses explicit delivery paths. ASTRA_BRIEF.md, inputs, raw PFR pages,
private pull data and .scratch stay uncommitted. No binary game data is shipped.

Final measured runs: exact 0.74 s / 84,196 KiB; rosters 29.22 s / 154,816 KiB; native 34.28 s / 112,180 KiB; integration 16.78 s / 167,552 KiB; panel 3.18 s / 70,420 KiB; regen 6.82 s / 163,428 KiB. All 46 standalone tests passed, with zero skips. The largest process used 167,552 KiB, below 2 GiB. Regeneration reproduced all 36 dataset files and both unchanged inventory files byte for byte.

## Commit fallback

The explicit 47-path staging attempt failed at the worktree index.lock with
`Read-only file system`. The authorized fallback is
`.scratch/espn25-exact-lineups.bundle`, based on
`5704832d83672028ed0966424d5f1ec71f690661`, with branch
`refs/heads/astra/r64-espn25-exact-lineups`. Separate local Git metadata under
scratch creates the commit using explicit add and commit paths. The original
worktree's HEAD stays at its base, and all delivered files remain in place.
The bundle's tree and changed-path list are checked against the 47 files;
verification and commit identity are recorded in
`.scratch/espn25-exact-lineups-delivery.json`. No remote fetch or push is used.

A coordinating checkout with the base commit can verify the bundle, fetch its
named branch from the local bundle, and cherry-pick the resulting commit.
The brief, raw evidence, inputs, scratch repository and scratch notes are not
part of the commit. The only protected-file handoff is the report allowlist
entry and the scheduled whole-stack cave-manifest regeneration in WIRING.md.
