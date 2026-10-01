# DESIGN: NFL 2K28 scheme research, 2026-09-24

PROVED OFFLINE: Status labels distinguish reproducible file/code checks (PROVED OFFLINE), proposed football/game behavior (DESIGN), and sourced interpretation without a game witness (INFERRED). A source reporting a fact does not establish engine behavior.

## PROVED OFFLINE: data and denominators

PROVED OFFLINE: [tendencies_2025.json](tendencies_2025.json) contains all 32 teams, exact numerators, denominators, source URLs, SHA-256 digests, and FTN retrieval timestamps. [aggregate.py](aggregate.py) reproduces it using Python's standard library. Inputs are the local r1 research cache, read without modification. Its fetch log records downloads on 2026-09-24. Sources: [nflverse PBP](https://github.com/nflverse/nflverse-data/releases/tag/pbp), [FTN charting](https://github.com/nflverse/nflverse-data/releases/tag/ftn_charting), [participation](https://github.com/nflverse/nflverse-data/releases/tag/pbp_participation).

PROVED OFFLINE: Include 2025 regular-season run/pass plays; exclude kneels/spikes. Join on game ID and integer play ID, refuse duplicate keys and possession mismatches. All included plays have both charting and personnel joins. PA divides by charted QB dropbacks, motion by charted offensive plays. Personnel counts FB with RB; six-OL, non-eleven-player and unusual QB packages are `other`. Percentages for 11/12/21 do not sum to 100 because other groups exist. PBP shotgun includes pistol; FTN pistol is shown separately and must not be added to shotgun. These are snap tendencies, not recommended menu weights. Sources: the three release files linked in the JSON and [FTN dictionary](https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html).

PROVED OFFLINE: The public FTN extract has motion, PA and U/S/P QB location; participation adds personnel and formation family. Neither file contains inside-zone, outside-zone, duo or counter labels, nor Trips/Bunch/Empty geometry. PBP `run_location` is direction, not a blocking scheme. Run-direction counts are retained in the JSON; no concept percentages are fabricated. Full FTN concept charting would be needed for those percentages. Sources: [FTN dictionary](https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html), [participation dictionary](https://nflreadr.nflverse.com/articles/dictionary_participation.html).

PROVED OFFLINE: No 2026 PBP/charting snapshot was present in the accessible cache. Shell download failed with DNS unavailable. This deliverable therefore contains measured 2025 tendencies and cited 2026 Giants reporting, not invented 2026 season rates. DESIGN: phase 2 uses this disclosed 2025 baseline; no 2026 charting rate is asserted. The missing 2026 rates and full run-concept charting remain research gaps.

## INFERRED: scheme families and current Giants direction

INFERRED: Shanahan's family pairs outside zone with related play-action looks, cutbacks and condensed spacing. Reid combines West Coast timing with spread presentations and repeated concepts. Coryell descendants emphasize vertical timing; modern branches blend systems. These are families, not mutually exclusive labels for teams. [Ruiz/Lee, February 2025](https://www.theringer.com/2025/02/04/nfl/nfl-play-calling-network-andy-reid-sean-mcvay-kyle-shanahan-hiring-cycle).

INFERRED: McVay should not be reduced to historical wide zone. The Rams' own retrospective describes a 2025 duo-centered attack with outside zone and skill-position blocking. [Rams, February 2026](https://www.therams.com/news/feature-how-the-rams-built-the-most-successful-designed-run-game-of-the-last-decade-in-2025). Coryell's historical offense also supported a substantial run game, as former Chargers players describe. [Chargers oral history](https://www.chargers.com/news/remembering-doug-wilkerson).

INFERRED: New York's 2026 staff is John Harbaugh, OC Matt Nagy, passing-game coordinator/QB coach Brian Callahan, senior offensive assistant Greg Roman, and TE coach Tim Kelly. This is a staff change; 2025 NYG rates are not Nagy's tendencies. [Official staff announcement](https://www.giants.com/news/john-harbaugh-announces-2026-coaching-staff-coordinators-matt-nagy-dennard-wilson-chris-horton).

INFERRED: Likely signed with New York in March. August camp reporting described multiple-TE/fullback sets on early downs and more 11 personnel in passing situations, with Likely capable of inline, slot and boundary alignments. This is qualitative camp evidence, not a season percentage. [Signing](https://www.giants.com/news/5-things-to-know-about-tight-end-isaiah-likely-baltimore-ravens-john-harbaugh-2026-nfl-free-agency-coastal-carolina), [camp](https://www.giants.com/news/training-camp-john-harbaugh-jaxson-dart-abdul-carter-isaiah-likely).

INFERRED: Likely described Roman-like run elements combined with Nagy, Kelly and Callahan contributions. Harbaugh described Likely winning on a stick-nod. That supports TE versatility, not an unverified numerical seam/drag target rate. [August 4 transcript](https://www.giants.com/news/quotes-8-4-coach-john-harbaugh-te-isaiah-likely-cb-paulson-adebo-s-tyler-nubin).

DESIGN: Build a Giants hybrid with substantial 12 personnel, gun quick/intermediate concepts, zone/gap runs and play action. Feature the TE1 role on seams, drags and crossers per Noah's request. TE1 is a depth-chart role, not a hard-coded player identity. Main must verify Likely actually fills it on the SOFTDRINK roster. Exclude RPO/read-option and adaptive option routes despite their presence in real offenses. No Madden binary assets or proprietary playbook dump are used.

## PROVED OFFLINE: every team's measured 2025 baseline

PROVED OFFLINE: Every numeric row below is calculated from the cited release files in [the source manifest and counts](tendencies_2025.json). N is eligible offensive snaps. Motion and PA denominators differ as described above. All values are percentages except N. Modern aliases: ARI=retail ARZ, LA=STL, LAC=SD, LV=OAK.

| Team | N | 11 | 12 | 21 | Gun incl. pistol | Pistol | Motion | PA/dropback |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ARI | 1074 | 46.5 | 29.1 | 0.0 | 71.4 | 2.5 | 43.9 | 24.6 |
| ATL | 1036 | 45.5 | 37.5 | 9.3 | 80.5 | 33.0 | 66.8 | 20.0 |
| BAL | 956 | 30.4 | 35.1 | 18.5 | 64.8 | 5.4 | 53.9 | 22.3 |
| BUF | 1065 | 62.2 | 11.4 | 7.7 | 49.8 | 1.4 | 60.3 | 25.6 |
| CAR | 996 | 66.5 | 20.4 | 1.9 | 66.9 | 7.4 | 42.8 | 21.9 |
| CHI | 1096 | 52.2 | 32.5 | 0.0 | 51.8 | 2.1 | 58.2 | 31.5 |
| CIN | 1049 | 64.5 | 29.5 | 1.8 | 82.0 | 3.0 | 53.1 | 15.9 |
| CLE | 1028 | 44.1 | 41.6 | 1.4 | 67.3 | 2.2 | 49.5 | 22.0 |
| DAL | 1104 | 67.5 | 17.2 | 8.0 | 62.5 | 1.9 | 59.1 | 26.8 |
| DEN | 1079 | 64.0 | 10.6 | 5.1 | 65.2 | 4.5 | 46.5 | 24.1 |
| DET | 1051 | 58.8 | 22.8 | 3.2 | 51.5 | 0.5 | 59.9 | 25.5 |
| GB | 993 | 56.6 | 32.7 | 3.1 | 62.9 | 7.2 | 55.2 | 25.4 |
| HOU | 1078 | 66.8 | 8.0 | 4.6 | 61.8 | 0.0 | 54.0 | 22.8 |
| IND | 1011 | 63.2 | 25.7 | 0.7 | 71.7 | 3.8 | 53.0 | 27.8 |
| JAX | 1074 | 66.3 | 18.9 | 3.5 | 60.7 | 3.1 | 60.1 | 21.8 |
| KC | 1048 | 56.8 | 28.3 | 4.3 | 80.7 | 3.5 | 49.8 | 15.2 |
| LA | 1056 | 59.7 | 8.9 | 0.0 | 41.0 | 0.7 | 64.9 | 34.6 |
| LAC | 1080 | 57.6 | 5.7 | 11.0 | 71.4 | 4.5 | 52.3 | 23.1 |
| LV | 942 | 57.6 | 33.3 | 0.3 | 66.1 | 3.0 | 52.3 | 24.8 |
| MIA | 942 | 36.2 | 9.6 | 24.4 | 71.4 | 19.0 | 70.6 | 27.4 |
| MIN | 943 | 64.8 | 19.9 | 7.8 | 55.7 | 0.6 | 52.0 | 25.6 |
| NE | 1017 | 49.9 | 20.2 | 15.7 | 55.0 | 0.2 | 53.0 | 24.1 |
| NO | 1064 | 66.9 | 11.2 | 0.4 | 78.8 | 2.9 | 61.6 | 18.5 |
| NYG | 1079 | 61.0 | 32.8 | 0.7 | 76.7 | 6.7 | 38.6 | 22.8 |
| NYJ | 1009 | 67.4 | 17.3 | 6.1 | 73.1 | 4.3 | 62.9 | 17.8 |
| PHI | 995 | 60.2 | 26.5 | 1.0 | 77.5 | 6.8 | 47.4 | 22.3 |
| PIT | 975 | 39.0 | 25.2 | 2.4 | 66.7 | 1.7 | 55.1 | 19.4 |
| SEA | 997 | 41.4 | 28.0 | 13.8 | 46.2 | 2.7 | 57.2 | 25.2 |
| SF | 1065 | 43.3 | 11.4 | 37.0 | 53.9 | 2.2 | 68.5 | 22.3 |
| TB | 1065 | 69.3 | 20.1 | 4.6 | 65.1 | 3.9 | 62.2 | 16.8 |
| TEN | 995 | 70.2 | 16.7 | 2.3 | 72.9 | 1.7 | 44.7 | 18.7 |
| WAS | 979 | 57.1 | 22.4 | 2.0 | 87.8 | 17.5 | 54.5 | 25.7 |

## DESIGN: phase 1 expansion gate (superseded by phase 2 approval)

DESIGN: Keep the numeric profiles separate from coaching genealogy. After main approves the Giants lab, use each team's measured personnel and QB-location distribution to choose formation proportions, then verify that team's 2026 staff and key players on its official site. Do not infer 2026 coaching continuity from a 2025 file. Vary routes, run direction, formation geometry and TE/RB emphasis, not just names. That was the phase 1 stopping point. Phase 2 is authorized by the 2026-09-24 evening brief.

INFERRED: The family article supports Shanahan for SF, McVay for LA, related branches for GB/MIA/MIN, Payton for DEN, and Coryell influences for IND/PHI/ARI at its February 2025 publication date. It also discusses Johnson's move to CHI and Coen's move to JAX. It does not establish their 2026 staff or current concept rates. [Family analysis](https://www.theringer.com/2025/02/04/nfl/nfl-play-calling-network-andy-reid-sean-mcvay-kyle-shanahan-hiring-cycle).

DESIGN: License this derived research table/JSON under CC-BY-SA-4.0 with attribution to nflverse and FTN Data. The playbook recipe is separately licensed CC0-1.0. Source terms: [FTN loader attribution and license](https://nflreadr.nflverse.com/reference/load_ftn_charting.html).

## DESIGN: phase 2 team design register

DESIGN: Main approved the phase 1 result and explicitly authorized the other 31 books. The following register drives [team_profiles.json](team_profiles.json). Staff and key-player associations are INFERRED from the linked official pages checked on 2026-09-24; the family classification and every concept emphasis are DESIGN interpretations, not measured 2026 concept frequencies. The scheme genealogy source above and the linked coaching biographies support those interpretations. New coordinators are named explicitly instead of assuming 2025 continuity.

DESIGN: Normalize the measured 2025 11/12/21 percentages over those three groups, add the disclosed personnel design biases, and apportion the available ordinary formation slots by largest remainder. Gun and pistol counts use separate shares (gun subtracts pistol); under center receives the remainder. Counts reflect menu design, not CPU call rates. Excluded personnel groups are not misreported as 11/12/21 snaps. NO, NYJ and TB lack a stock 12 group with an HB: their 12 allocation goes to 11, preserving all personnel payloads. PIT and MIN use an existing unused stock category when needed.

DESIGN: Each family weights its core concepts, each team's explicit emphasis adds further weight, and HB1/TE1 features add screen or seam/drag calls. A weighted fair selector fills each menu without repeating a concept. The feature role also determines fixed first reads when it has a route. Width and depth steps are authored spacing choices. QB read ordinals, handoff targets and fake-handoff targets move with the native role permutation; TE1 is not universally slot 6.

DESIGN: The named players motivate role choices only. No pack alters the roster or promises a player's depth order, health, game availability or stats. Main must check the actual SOFTDRINK roster. The Giants remain the approved phase 1 pack. True motion/jet, duo combos, middle screens, RPO and read option remain excluded as documented in CONCEPTS.md.

| Team | INFERRED staff / source | DESIGN family | INFERRED players / source | DESIGN feature; extra concept emphasis | DESIGN personnel bias; width; depth step |
| --- | --- | --- | --- | --- | --- |
| ARZ | [Mike LaFleur / Nathaniel Hackett](https://www.azcardinals.com/team/coaches-roster/mike-lafleur) | McVay/LaFleur condensed zone | [Trey McBride; Marvin Harrison Jr.](https://www.azcardinals.com/team/depth-chart) | TE1: Trey McBride; TE Seam, TE Drag, Y Cross | 12 +8; 0.9; 2 |
| ATL | [Kevin Stefanski / Tommy Rees](https://www.atlantafalcons.com/team/coaches-roster/tommy-rees) | Stefanski zone and play action | [Bijan Robinson; Kyle Pitts Sr.](https://www.atlantafalcons.com/team/depth-chart) | HB1: Bijan Robinson; Outside Zone, RB Slip, PA Boot | 12 +5; 0.95; 1 |
| BAL | [Declan Doyle](https://www.baltimoreravens.com/news/ravens-name-declan-doyle-offensive-coordinator) | Johnson/Payton heavy personnel blend | [Derrick Henry; Mark Andrews; Lamar Jackson](https://www.baltimoreravens.com/team/depth-chart) | TE1: Mark Andrews; Downhill, Counter, TE Seam | 12 +3; 0.9; 1 |
| BUF | [Joe Brady / Pete Carmichael](https://www.buffalobills.com/news/bills-name-pete-carmichael-as-offensive-coordinator) | Payton/Brady spread timing | [James Cook III; Dalton Kincaid; Josh Allen](https://www.buffalobills.com/team/depth-chart) | HB1: James Cook III; Inside Zone, RB Slip, Levels | none; 1.05; 2 |
| CAR | [Dave Canales / Brad Idzik](https://www.panthers.com/news/dave-canales-offensive-coordinator-brad-idzik-to-call-plays-in-2026) | Canales West Coast zone | [Tetairoa McMillan; Chuba Hubbard](https://www.panthers.com/team/depth-chart) | WR1: Tetairoa McMillan; Outside Zone, Stick, Drive | none; 1.0; 1 |
| CHI | [Ben Johnson / Press Taylor](https://www.chicagobears.com/news/press-taylor-excited-for-new-opportunity-as-bears-offensive-coordinator) | Johnson multiple gap and play action | [Colston Loveland; Rome Odunze](https://www.chicagobears.com/team/depth-chart) | TE1: Colston Loveland; Counter, PA Boot, TE Seam | none; 0.85; 2 |
| CIN | [Zac Taylor / Dan Pitcher](https://www.bengals.com/team/coaches-roster/) | Taylor spread passing | [Ja'Marr Chase; Tee Higgins](https://www.bengals.com/team/depth-chart) | WR1: Ja'Marr Chase; Dagger, Levels, Mesh | none; 1.1; 2 |
| CLE | [Todd Monken / Travis Switzer](https://www.clevelandbrowns.com/news/browns-finalize-the-2026-coaching-staff) | Monken vertical and gap blend | [Harold Fannin Jr.; Quinshon Judkins](https://www.clevelandbrowns.com/team/depth-chart) | TE1: Harold Fannin Jr.; TE Seam, Counter, Y Cross | 11 +5; 0.95; 2 |
| DAL | [Brian Schottenheimer / Klayton Adams](https://www.dallascowboys.com/team/coaches-roster/klayton-adams) | Schottenheimer vertical timing | [CeeDee Lamb; George Pickens](https://www.dallascowboys.com/team/depth-chart) | WR1: CeeDee Lamb; Dagger, Drive, Inside Zone | none; 1.05; 1 |
| DEN | [Sean Payton / Davis Webb](https://www.denverbroncos.com/news/head-coach-sean-payton-names-davis-webb-as-offensive-coordinator-and-logan-kilgore-as-quarterbacks-coach) | Payton West Coast progression | [Courtland Sutton; Bo Nix](https://www.denverbroncos.com/team/depth-chart) | WR1: Courtland Sutton; Stick, Levels, Mesh | none; 1.0; 0 |
| DET | [Dan Campbell / Drew Petzing](https://www.detroitlions.com/news/5-things-to-know-about-new-oc-drew-petzing) | Petzing gap/zone and TE matchups | [Jahmyr Gibbs; Sam LaPorta](https://www.detroitlions.com/team/depth-chart) | HB1: Jahmyr Gibbs; RB Slip, Counter, TE Seam | 12 +8; 0.95; 1 |
| GB | [Matt LaFleur / Adam Stenavich](https://www.packers.com/news/packers-announce-coaching-staff-changes-march-19-2026) | LaFleur wide zone and verticals | [Josh Jacobs; Tucker Kraft](https://www.packers.com/team/depth-chart) | TE1: Tucker Kraft; Outside Zone, TE Seam, Dagger | none; 0.95; 2 |
| HOU | [Nick Caley](https://www.houstontexans.com/team/coaches-roster/) | McVay/Patriots structured passing | [Nico Collins; C.J. Stroud](https://www.houstontexans.com/video/nico-collins-on-c-j-stroud-the-wr-room-and-otas-full-q-a) | WR1: Nico Collins; Dagger, Levels, PA Boot | none; 0.95; 2 |
| IND | [Shane Steichen / Jim Bob Cooter](https://www.colts.com/news/colts-announce-2026-coaching-staff-marian-hobby-defensive-line-lou-anarumo) | Steichen vertical and zone | [Jonathan Taylor; Tyler Warren](https://www.colts.com/team/depth-chart) | TE1: Tyler Warren; Inside Zone, TE Seam, Y Cross | none; 1.0; 2 |
| JAX | [Liam Coen / Grant Udinski](https://www.jaguars.com/news/k00022-jaguars-retain-offensive-coordinator-grant-udinski-defensive-coordinator-anthony-campanile) | Coen McVay multiple | [Brian Thomas Jr.; Trevor Lawrence](https://www.jaguars.com/team/depth-chart) | WR1: Brian Thomas Jr.; Dagger, Downhill, Flood | none; 0.9; 1 |
| KC | [Andy Reid / Eric Bieniemy](https://www.chiefs.com/team/coaches-roster/eric-bieniemy) | Reid West Coast spread | [Travis Kelce; Rashee Rice; Patrick Mahomes](https://www.chiefs.com/team/depth-chart) | TE1: Travis Kelce; Mesh, Stick, RB Slip | none; 1.0; 0 |
| MIA | [Bobby Slowik](https://www.miamidolphins.com/team/coaches-roster/bobby-slowik) | Shanahan/Slowik zone | [De'Von Achane](https://www.miamidolphins.com/team/depth-chart) | HB1: De'Von Achane; Outside Zone, RB Slip, End Around | 11 +8; 0.85; 0 |
| MIN | [Kevin O'Connell / Wes Phillips](https://www.vikings.com/news/2026-coaching-staff-updates-promotions-hires) | McVay wide zone and crossers | [Justin Jefferson; T.J. Hockenson](https://www.vikings.com/team/depth-chart) | WR1: Justin Jefferson; Y Cross, Dagger, Outside Zone | none; 0.95; 2 |
| NE | [Josh McDaniels](https://www.patriots.com/team/coaches-roster/josh-mcdaniels) | Erhardt-Perkins fixed progression subset | [Hunter Henry; Drake Maye](https://www.patriots.com/team/depth-chart) | TE1: Hunter Henry; Levels, TE Seam, Drive | none; 1.0; 1 |
| NO | [Kellen Moore / Doug Nussmeier](https://www.neworleanssaints.com/team/coaches-roster/doug-nussmeier) | Moore vertical and quick game | [Chris Olave; Tyler Shough](https://www.neworleanssaints.com/team/depth-chart) | WR1: Chris Olave; Levels, Dagger, RB Slip | none; 1.05; 1 |
| NYG | [Matt Nagy / Greg Roman](https://www.giants.com/news/john-harbaugh-announces-2026-coaching-staff-coordinators-matt-nagy-dennard-wilson-chris-horton) | Nagy/Roman TE hybrid | [Isaiah Likely; Jaxson Dart](https://www.giants.com/team/depth-chart) | TE1: Trey McBride; TE Seam, TE Drag, Y Cross | 12 +25; 1.0; 0 |
| NYJ | [Frank Reich](https://www.newyorkjets.com/team/coaches-roster/frank-reich) | Reich West Coast vertical blend | [Garrett Wilson; Breece Hall](https://www.newyorkjets.com/team/depth-chart) | WR1: Garrett Wilson; Drive, RB Slip, Dagger | none; 1.05; 1 |
| OAK | [Klint Kubiak / Andrew Janocko](https://www.raiders.com/news/raiders-announce-2026-coaching-staff) | Kubiak wide zone | [Brock Bowers; Ashton Jeanty](https://www.raiders.com/team/depth-chart) | TE1: Brock Bowers; TE Seam, Outside Zone, TE Drag | 12 +5; 0.85; 1 |
| PHI | [Sean Mannion](https://www.philadelphiaeagles.com/team/coaches/sean-mannion) | LaFleur branch with downhill core | [Saquon Barkley; DeVonta Smith](https://www.philadelphiaeagles.com/team/depth-chart) | WR1: Saquon Barkley; Downhill, Outside Zone, PA Boot | 12 +3; 0.95; 2 |
| PIT | [Mike McCarthy / Brian Angelichio](https://www.steelers.com/news/steelers-complete-2026-coaching-staff) | McCarthy West Coast | [DK Metcalf; Pat Freiermuth](https://www.steelers.com/team/depth-chart) | WR1: DK Metcalf; Drive, Levels, TE Seam | 11 +8; 1.05; 2 |
| SD | [Mike McDaniel](https://www.chargers.com/team/coaches-roster/mike-mcdaniel) | McDaniel wide zone and crossers | [Ladd McConkey; Justin Herbert](https://www.chargers.com/team/depth-chart) | WR1: Ladd McConkey; Outside Zone, Y Cross, RB Slip | 11 +5; 0.85; 1 |
| SEA | [Brian Fleury](https://www.seahawks.com/news/seahawks-hire-offensive-coordinator-brian-fleury) | Shanahan/Fleury zone and play action | [Jaxon Smith-Njigba; Sam Darnold](https://www.seahawks.com/team/depth-chart) | WR1: Jaxon Smith-Njigba; Outside Zone, PA Boot, Drive | none; 0.9; 2 |
| SF | [Kyle Shanahan / Klay Kubiak](https://www.49ers.com/news/day-3-of-49ers-camp-2026-key-takeaways-from-wednesday-s-practice) | Shanahan wide zone with fullback | [Christian McCaffrey; George Kittle; Kyle Juszczyk](https://www.49ers.com/team/depth-chart) | HB1: Bijan Robinson; Outside Zone, RB Slip, PA Boot | none; 0.85; 1 |
| STL | [Sean McVay / Nate Scheelhaase](https://www.therams.com/team/coaches-roster/nate-scheelhaase) | McVay condensed downhill | [Puka Nacua; Kyren Williams](https://www.therams.com/team/depth-chart) | WR1: Puka Nacua; Downhill, Dagger, PA Boot | none; 0.8; 2 |
| TB | [Zac Robinson](https://www.buccaneers.com/news/buccaneers-offensive-preview-training-camp-2026) | McVay/Robinson condensed passing | [Emeka Egbuka; Bucky Irving](https://www.buccaneers.com/team/depth-chart) | WR1: Emeka Egbuka; Levels, RB Slip, Dagger | 12 +7; 0.9; 1 |
| TEN | [Brian Daboll](https://www.tennesseetitans.com/team/coaches-roster/brian-daboll) | Daboll spread progression | [Cam Ward; Calvin Ridley](https://www.tennesseetitans.com/team/depth-chart) | WR1: Cam Ward; Mesh, Stick, Levels | 11 +4; 1.1; 0 |
| WAS | [David Blough](https://www.commanders.com/news/commanders-name-david-blough-offensive-coordinator) | Blough multiple spread design | [Terry McLaurin; Jayden Daniels](https://www.commanders.com/team/depth-chart) | WR1: Terry McLaurin; Mesh, Drive, Y Cross | 12 +3; 1.05; 1 |

INFERRED: Green Bay player context also uses [Jacobs roster biography](https://www.packers.com/team/players-roster/josh-jacobs/). This is a role-design reference, not a claim that he is available for the next game. The public Texans depth chart is an image, so its player reference uses the linked team interview instead.
