# ESPN 25th Anniversary real roster data patch, r64

2026-09-07. Base `76434d6108a25ca7deac0160fb05f717badd7bd0`, branch
`astra/r64-espn25-rosters`. **EXPERIMENTAL / UNWITNESSED. Opt-in only.**

The 35 shared files now carry the box-score starters of their chosen moments,
with season jersey numbers from Pro Football Reference and the attributed
nflverse base. All **770 chosen-side starters** occupy starting depth slots.
**1,732 of 1,855 numbers** are supported by those season pages; **123 remain
unknown**. The fixed position mix still needs **105 players from other seasons**
and 18 same-season nflverse players absent from the PFR page. Fifteen sides in
12 moments share a file chosen for another season and cannot carry all of that
game's starters. Every exception is explicit in the manifest.

The existing Build and Gameplay Patches option is already wired in this base.
The data change keeps its names, numbers and colleges byte contract, with
positions, ratings, appearance, rank/side fields and team pointers preserved.
The sections labeled "Original" below retain the initial implementation's
evidence and counts; the following section and current per-moment table
supersede their season-only selection results and old dataset receipts.

## Exact lineups

Updated 2026-09-08. **EXPERIMENTAL / UNWITNESSED.** Source: **Pro Football
Reference** box-score starters and season roster pages, supplied offline in
`pfr_pull/v1`. Its 2,889 rows include 50 Team Total rows, leaving 2,839 players,
2,837 with numbers. Only derived player facts and source citations are shipped;
raw pages and the pull stay private. The nflverse CC-BY attribution remains the
separate base attribution and does not label the PFR source as CC-BY.

The generator reserves each chosen game's 22 starters first. Left and right
positions use the retail rank and side chains. Repeated TE/WR/DB roles use the
next available depth for that role. Bench players follow season games started,
games, then AV within the fixed position mix. When that cannot fill 53, the
manifest identifies same-season nflverse or nearest-season same-franchise
reserves. Numbers come only from the relevant PFR season page; 127 former
other-season number guesses are gone. Colleges fill blank CSV cells when the
PFR spelling matches one main-table college; 1,080 college cells can now be
encoded, up from 29.

All 1,100 box-score names match their game's season page. In the actual shared
files, 966 are present and 903 occupy starting depth; 770 of those belong to the
35 chosen sides. Thirteen moments have both sides complete. Fifteen losing
sides list missing starters, displaced starters and number mismatches.
`exact_game_lineup_established` is true for 35 sides only. **E** means
"exact game starters from the box score; bench from the season roster";
it describes the evidence basis, with shared-file exceptions shown per side.
It does not establish snap-specific players, injuries or substitutions.

Two source decisions need special attention: The Heartbreaker's supplied
box-score away/home labels run opposite to SITU and are bound by team name.
SAME OLD BUCS lists Lance Smith as SS, while the season page says RG; RG fills
the missing offensive guard and is explicitly a HYPOTHESIS correction. Houston's
1991 box score lists two RDE starters, so both are retained at the first two
right-end depths. Jim Otto's source number `00` is stored as numeric zero;
this writer cannot establish whether the game renders `00` or `0`.

See [the exact-lineup report](ASTRA_ESPN25_EXACT_LINEUPS_REPORT.md) for the
full before/after counts, every unresolved name, source decisions, final tests,
and Noah's three-moment witness list. Current dataset SHA-256:
`9f2c1d1d67ef630300a081410129c71a53f9de54f4b02a89ec0cbe7087656ba8`.

## Original source evidence and inventory

The input is the user's USA retail XISO/extraction plus 45 supplied
`inputs/nflverse_rosters/roster_1960.csv` through `roster_2004.csv`: **69,253 rows**.
Attribution: **nflverse contributors, nflverse-data season rosters,
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)**, supplied offline from
the [nflverse roster release](https://github.com/nflverse/nflverse-data/releases/tag/rosters).
These URLs are source/attribution identifiers, not network research performed in
this session. The generator follows the existing team-history tool's attribution
and era-code resolver. All 45 input digests, row counts, available columns and
nonempty-column counts are in the manifest. No input is fetched at generation,
validation or runtime.

The source has position membership, status and limited experience/draft metadata.
It has **no games-started column, depth ordinal, game lineup, Hall of Fame,
All-Pro or Pro Bowl signal**. `depth_chart_position` describes a role, not a
first/second-string ranking. `draft_round` is absent; supplied `draft_number`,
entry/rookie year and experience are incomplete. Source status is a season-list
attribute, not proof that someone was active on a game's date. The modern rows'
week/game-type fields do not provide the historic game lineups. No player-start
statistics or award flags are invented.

All 75 historical descriptors were independently decoded through the existing
`RosterDocument`/84-byte player codec. Their generated UTF-16 filename CRCs match
distinct archive entries 113..187. Each contains one team, 53 primary players,
zero secondary players, an uncompressed 32-byte wrapper, and a bounded name pool.
All 75 codec round trips preserve the original bytes. The 50 moment-side bindings
agree exactly with the parallel scenario session's read-only `bindings.json` and
research memo. No file in that worktree was changed or imported as a runtime
dependency. The native helper here is self-contained.

| Inventory scope | Files | Player slots | Placeholders | Names matching supplied identities | Unresolved retail names |
| --- | ---: | ---: | ---: | ---: | ---: |
| All historical resources | 75 | 3,975 | 3,330 | 643 | 2 |
| Resources used by these moments | 35 | 1,855 | 1,560 | 294 | 1 |
| Other resources, unchanged | 40 | 2,120 | 1,770 | 349 | 1 |

[The inventory CSV](docs/mod_editor/nfl2k5_espn25_inventory.csv) lists every file,
team, filename year and all 53 names, positions, numbers and 28 rating/style bytes.
[The inventory JSON](docs/mod_editor/nfl2k5_espn25_inventory.json) gives each
descriptor, resource size/hash/wrapper, position mix, name-pool boundary and
classification totals. A placeholder has the team's selector as its first name
(including the retail Buccanneers spelling) or a recognized position label as
its last name. Other names are matched against supplied full/legal names;
unmatched names stay unresolved, not declared fictitious. These are membership
matches, not proof of a particular season or starting role.

The two unresolved retail spellings are `Dave Binn` in unused outer 170 and
`Billy Lafleur` in used outer 174. The generated identities always come from the
source, even when replacing an unresolved name. 281 original slot identities
are retained where the supplied chosen-season membership and role support them.
The original partial scratch note that described every retail player as a
placeholder was incorrect; the full inventory above supersedes it.

## Original season-only selection rules (superseded)

1. **Choose a roster season for the shared file.** Parse the retail moment's date;
   January/February belong to the preceding season. Prefer a using moment whose
   season matches the filename year, then one whose calendar year matches, then
   the nearest season; the lower moment index breaks ties. A file used by only
   one moment takes that game's season, even when the filename advertises a very
   different year. Filenames, descriptors, kit choices, SITU titles/dates and
   bindings remain unchanged. File-year text is a resource identity, not proof
   of the appropriate lineup. For example, `h-11-1970-colts-5` gets 1997 Colts
   players for moment 19.
2. **Assign 53 distinct supplied identities to the existing roles.** Identity is
   normalized first name, last name and birth date. A deterministic bounded
   minimum-cost assignment reserves scarce role matches and maximizes compatible
   chosen-season identities before using nearby seasons. Broad RB/DB/LB/OL/DL,
   historical E, NT, LS and related source roles map only into their documented
   compatible retail roles. No unrelated-position filler is used. The output has
   1,308 exact-role matches, 480 broad source-role matches and 67 same-family
   concessions, disclosed per player. Regular-season candidates are placed ahead
   of fillers within each position's existing depth ranks.
3. **Use conservative starter proxies.** Compatible real retail slot identities
   in the chosen season receive preference. Otherwise source-matched narrative
   names, status, available starts (none here), recent four-season franchise
   tenure, available experience/inferred career length and draft information
   provide a weak ranking. Exact role and existing number agreement help resolve
   the assignment. This is a deterministic inference about season regulars,
   never a verified game starting lineup or exact on-field personnel set.
4. **Document three editorial quarterback preferences as HYPOTHESIS.** The tenure
   heuristic otherwise favors long-serving backups. QB depth rank zero prefers
   Daryle Lamonica for 1968 Oakland, Dan Fouts for 1981 San Diego, and Dave Krieg
   for 1992 Kansas City. Every preferred identity is required to exist in that
   team's supplied chosen-season QB rows. Their priority is an editorial judgment,
   not supplied game-start evidence or a newly verified historical fact. No other
   hand-entered names or external roster are used.
5. **Disclose missing membership.** Selected-season lists range from 41 to 110
   distinct players; even a list with more than 53 can lack a compatible role.
   The 105 role fillers are real supplied players from the same franchise,
   at most four seasons away. They are explicitly **not established members of
   the selected game's roster**. No fictional name, duplicate identity, shortened
   surname or borrowed other-franchise player fills a gap. Nate Hobgood-Chittick
   in the 1999 Rams source is excluded because his surname exceeds the existing
   15-character codec; that exclusion and source row are in the manifest.
6. **Numbers stay evidence-qualified.** 555 values come from the selected player's
   source row. For 127 missing values, use the nearest available season number of
   the same identity and franchise; these are uncertain and can be as far as
   13 years away. The remaining 1,173 retain the retail slot number and are labeled
   unknown. Source zero means missing. Every output number is a valid 0..99 codec
   value; number validity does not mean historical correctness or uniqueness.
   The 555 source-row values include rows used as season fillers, so that count
   does not certify 555 numbers for a particular game either.
7. **Preserve all 28 rating/style bytes exactly.** No supplied award signal exists,
   so there are no rating adjustments. Existing bytes above 100 are retained on
   disc; native `C1030` clamps the imported values to 0..100. Position code, rank,
   side, physical appearance, height/weight, age, equipment, face, photo/commentary,
   contract and all other bits remain those of the retail slot. A correct name
   therefore does not imply a matching face, body, equipment or commentary.
8. **College means a main-table index.** For 29 records, the supplied college string
   matches exactly one of the main roster's 266 college strings and is encoded
   as its zero-based index. The other 1,826 retain their original word. Historic
   records do not use the ordinary field-relative college pointer setter. The
   bounded native trace verifies the resulting live college pointers.

The [manifest](data/nfl2k5_espn25_moment_rosters/manifest.json) records each output
slot's exact input filename/line, full name, source season/team/status/role,
identity key, number donor, college basis, retail depth rank and all exceptions.
Each generated CSV uses the existing `RosterDocument` CSV column names, with
primary indices 0..52, complete editable names/numbers/positions/colleges and all
rating/style columns. The importer accepts this existing sparse CSV format.

## Per-moment game, file mapping and lineup basis

Indices are the native **0..24** order, corresponding to menu positions 1..25.
Teams below are the real-game franchise names; away/home means the game's SITU
side, including neutral-site Super Bowls. Dates and titles are retained from the
user's retail SITU. The title `LONGEST PLAYOFF GAME EVER` is a retail caption,
not an independently verified record claim.

Every row uses **E: exact game starters from the box score; bench from the
season roster**, with the shared-file losses shown explicitly. S is starters
resolved at starting depth (out of 22), N is numbers verified against this
moment's game-season page, and U is numbers still unverified for this moment.
F counts other-season players in the loaded file. P counts replaced retail
placeholders. Pairs are away/home in SITU order. N/U totals repeat shared files;
unique-resource totals are 1,732/123, while moment-side totals are 2,060/590.

| Index / title | Game date; teams | Away file; selected season | Home file; selected season | Lineup basis and shared loss | S A/H | N; U; F; P A/H |
| --- | --- | --- | --- | --- | ---: | --- |
| 0: THE ICE BOWL | 1967-12-31; Dallas Cowboys vs Green Bay Packers | `h-07-1971-cowboys-4.iff`; 1967 | `h-10-1966-packers-3.iff`; 1967 | E. Both sides complete. | 22/22 | N 41/41; U 12/12; F 12/12; P 53/53 |
| 1: THE HEIDI BOWL | 1968-11-17; New York Jets vs Oakland Raiders | `h-19-1968-jets-4.iff`; 1968 | `h-20-1967-raiders-1.iff`; 1968 | E. Both sides complete. | 22/22 | N 44/49; U 9/4; F 8/4; P 53/53 |
| 2: MERRY CHRISTMAS MIAMI | 1971-12-25; Miami Dolphins vs Kansas City Chiefs | `h-14-1972-dolphins-4.iff`; 1971 | `h-13-1969-chiefs-4.iff`; 1971 | E. Both sides complete. | 22/22 | N 44/44; U 9/9; F 8/9; P 53/53 |
| 3: THE IMMACULATE RECEPTION | 1972-12-23; Oakland Raiders vs Pittsburgh Steelers | `h-20-1967-raiders-1.iff`; 1968 | `h-22-1975-steelers-1.iff`; 1972 | E. away uses 1968 for 1972 | 6/22 | N 13/47; U 40/6; F 4/5; P 53/53 |
| 4: THE SEA OF HANDS | 1974-12-21; Miami Dolphins vs Oakland Raiders | `h-14-1972-dolphins-4.iff`; 1971 | `h-20-1976-raiders-0.iff`; 1974 | E. away uses 1971 for 1974 | 15/22 | N 29/47; U 24/6; F 8/6; P 53/53 |
| 5: THE FINAL COMEBACK | 1979-12-16; Washington Redskins vs Dallas Cowboys | `h-29-1982-redskins-2.iff`; 1983 | `h-07-1977-cowboys-3.iff`; 1979 | E. away uses 1983 for 1979 | 7/22 | N 11/44; U 42/9; F 3/9; P 53/53 |
| 6: THE AINTS' BIGGEST CHOKE | 1980-12-07; New Orleans Saints vs San Francisco 49ers | `h-17-1991-saints-4.iff`; 1980 | `h-25-1981-49ers-3.iff`; 1981 | E. home uses 1981 for 1980 | 22/13 | N 51/27; U 2/26; F 2/0; P 52/53 |
| 7: LONGEST PLAYOFF GAME EVER | 1982-01-02; San Diego Chargers vs Miami Dolphins | `h-24-1980-chargers-4.iff`; 1981 | `h-14-1984-dolphins-3.iff`; 1981 | E. Both sides complete. | 22/22 | N 48/48; U 5/5; F 4/5; P 53/53 |
| 8: THE CATCH | 1982-01-10; Dallas Cowboys vs San Francisco 49ers | `h-07-1977-cowboys-3.iff`; 1979 | `h-25-1981-49ers-3.iff`; 1981 | E. away uses 1979 for 1981 | 10/22 | N 28/53; U 25/0; F 9/0; P 53/53 |
| 9: GREATEST REDSKIN COMEBACK | 1983-10-02; Los Angeles Raiders vs Washington Redskins | `h-20-1983-raiders-0.iff`; 1983 | `h-29-1982-redskins-2.iff`; 1983 | E. Both sides complete. | 22/22 | N 52/50; U 1/3; F 1/3; P 53/53 |
| 10: THE DRIVE | 1987-01-11; Denver Broncos vs Cleveland Browns | `h-08-1986-broncos-1.iff`; 1986 | `h-30-1986-browns-1.iff`; 1986 | E. Both sides complete. | 22/22 | N 52/50; U 1/3; F 0/3; P 53/53 |
| 11: THE 2-SECOND MISCALCULATION | 1987-09-20; San Francisco 49ers vs Cincinnati Bengals | `h-25-1989-49ers-3.iff`; 1988 | `h-06-1988-bengals-1.iff`; 1988 | E. away uses 1988 for 1987; home uses 1988 for 1987 | 11/11 | N 39/40; U 14/13; F 0/2; P 51/53 |
| 12: SAME OLD BUCS | 1987-11-08; Tampa Bay Buccaneers vs St. Louis Cardinals | `h-27-1979-buccaneers-3.iff`; 1987 | `h-00-1975-cardinals-3.iff`; 1987 | E. Both sides complete. Lance Smith RG correction. | 22/22 | N 53/53; U 0/0; F 0/0; P 53/53 |
| 13: 49ERS DO IT AGAIN | 1989-01-22; Cincinnati Bengals vs San Francisco 49ers | `h-06-1988-bengals-1.iff`; 1988 | `h-25-1989-49ers-3.iff`; 1988 | E. Both sides complete. | 22/22 | N 51/52; U 2/1; F 2/0; P 53/51 |
| 14: WIDE RIGHT | 1991-01-27; Buffalo Bills vs New York Giants | `h-03-1990-bills-2.iff`; 1990 | `h-18-1990-giants-2.iff`; 1990 | E. Both sides complete. | 22/22 | N 52/50; U 1/3; F 1/3; P 53/52 |
| 15: HOUSTON'S HEARTS RIPPED OUT | 1992-01-04; Houston Oilers vs Denver Broncos | `h-28-1979-oilers-2.iff`; 1991 | `h-08-1986-broncos-1.iff`; 1986 | E. home uses 1986 for 1991 Two source RDEs. | 22/5 | N 45/13; U 8/40; F 5/0; P 53/53 |
| 16: THE TWO TD COMEBACK ON KC | 1992-10-04; Kansas City Chiefs vs Denver Broncos | `h-13-1993-chiefs-2.iff`; 1992 | `h-08-1986-broncos-1.iff`; 1986 | E. home uses 1986 for 1992 | 22/5 | N 51/10; U 2/43; F 0/0; P 51/53 |
| 17: THE BIGGEST COMEBACK EVER | 1993-01-03; Houston Oilers vs Buffalo Bills | `h-28-1979-oilers-2.iff`; 1991 | `h-03-1990-bills-2.iff`; 1990 | E. away uses 1991 for 1992; home uses 1990 for 1992 | 17/11 | N 38/35; U 15/18; F 5/1; P 53/53 |
| 18: THE HEARTBREAKER | 1994-10-17; Denver Broncos vs Kansas City Chiefs | `h-08-1986-broncos-1.iff`; 1986 | `h-13-1993-chiefs-2.iff`; 1992 | E. away uses 1986 for 1994; home uses 1992 for 1994 | 2/7 | N 4/16; U 49/37; F 0/0; P 53/51 |
| 19: THE COLTS' COLLAPSE | 1997-09-21; Indianapolis Colts vs Buffalo Bills | `h-11-1970-colts-5.iff`; 1997 | `h-03-1990-bills-2.iff`; 1990 | E. home uses 1990 for 1997 | 22/2 | N 52/5; U 1/48; F 0/1; P 53/53 |
| 20: THE SUPER BOWL DRIVE | 1998-01-25; Green Bay Packers vs Denver Broncos | `h-10-1996-packers-2.iff`; 1997 | `h-08-1998-broncos-0.iff`; 1997 | E. Both sides complete. | 22/22 | N 52/53; U 1/0; F 1/0; P 42/36 |
| 21: A YARD TOO SHORT | 2000-01-30; St. Louis Rams vs Tennessee Titans | `h-23-1999-rams-2.iff`; 1999 | `h-28-1999-titans-0.iff`; 1999 | E. Both sides complete. | 22/22 | N 52/52; U 1/1; F 1/0; P 25/32 |
| 22: VINATIERI STRIKES AGAIN | 2002-02-03; St. Louis Rams vs New England Patriots | `h-23-1999-rams-2.iff`; 1999 | `h-16-2001-patriots-0.iff`; 2001 | E. away uses 1999 for 2001 | 11/22 | N 20/53; U 33/0; F 1/0; P 25/19 |
| 23: THE BOTCHED SNAP | 2003-01-05; New York Giants vs San Francisco 49ers | `h-18-2003-giants-0.iff`; 2002 | `h-25-2003-49ers-0.iff`; 2002 | E. Both sides complete. | 22/22 | N 52/51; U 1/2; F 0/0; P 17/9 |
| 24: FOURTH AND TWENTY-SIX | 2004-01-11; Green Bay Packers vs Philadelphia Eagles | `h-10-2004-packers-0.iff`; 2003 | `h-21-2004-eagles-0.iff`; 2003 | E. Both sides complete. | 22/22 | N 52/51; U 1/2; F 0/1; P 3/5 |

There are **15 mismatched sides in 12 moments**. The chosen and losing moments
are explicit below. A single shared file cannot switch its players by game date:
for example, moment 17's Bills load the chosen 1990 profile with Jim Kelly at QB1,
and moment 18's Chiefs load the chosen 1992 profile with Dave Krieg at QB1. This
must not be presented as either game's exact lineup. Cloning would need separate
ROST entries, new selectors and main historic descriptor/string growth; that is
outside this fixed-span option. The same file's historic exhibition team also
receives these replacement identities.

## Original unique resource decisions and byte counts (superseded)

The filename contains the original descriptor year. `Season` is the actual
selected data season. `Source` is the distinct supplied team-season membership
count before fitting roles, exclusions and fillers. QB1 is the name assigned to
the retained depth-rank-zero QB slot, not a claim about a game's starter. Every
CSV has 53 rows. Each listed file maps to the same basename under
`data/nfl2k5_espn25_moment_rosters/`, with `.csv` replacing `.iff`.

| Outer / filename | Season / QB1 | Source | F / U / O | Chosen moment; losing moments | Changed bytes |
| --- | --- | ---: | ---: | --- | ---: |
| 113: `h-00-1975-cardinals-3.iff` | 1987 / Neil Lomax | 88 | 0 / 53 / 0 | 12; none | 754 |
| 118: `h-03-1990-bills-2.iff` | 1990 / Jim Kelly | 57 | 1 / 46 / 4 | 14; 17, 19 | 722 |
| 124: `h-06-1988-bengals-1.iff` | 1988 / Boomer Esiason | 55 | 2 / 50 / 2 | 13; 11 | 720 |
| 125: `h-07-1971-cowboys-4.iff` | 1967 / Don Meredith | 41 | 12 / 52 / 1 | 0; none | 721 |
| 126: `h-07-1977-cowboys-3.iff` | 1979 / Roger Staubach | 47 | 9 / 43 / 10 | 5; 8 | 758 |
| 129: `h-08-1986-broncos-1.iff` | 1986 / John Elway | 53 | 1 / 52 / 0 | 10; 15, 16, 18 | 715 |
| 130: `h-08-1998-broncos-0.iff` | 1997 / John Elway | 63 | 0 / 0 / 0 | 20; none | 872 |
| 133: `h-10-1966-packers-3.iff` | 1967 / Bart Starr | 43 | 12 / 52 / 0 | 0; none | 708 |
| 134: `h-10-1996-packers-2.iff` | 1997 / Brett Favre | 67 | 1 / 0 / 0 | 20; none | 818 |
| 135: `h-10-2004-packers-0.iff` | 2003 / Brett Favre | 64 | 0 / 0 / 0 | 24; none | 667 |
| 136: `h-11-1970-colts-5.iff` | 1997 / Jim Harbaugh | 68 | 0 / 0 / 0 | 19; none | 820 |
| 139: `h-13-1969-chiefs-4.iff` | 1971 / Len Dawson | 45 | 9 / 52 / 1 | 2; none | 707 |
| 140: `h-13-1993-chiefs-2.iff` | 1992 / Dave Krieg | 67 | 0 / 37 / 12 | 16; 18 | 700 |
| 141: `h-14-1972-dolphins-4.iff` | 1971 / Bob Griese | 45 | 9 / 52 / 0 | 2; 4 | 706 |
| 142: `h-14-1984-dolphins-3.iff` | 1981 / David Woodley | 53 | 4 / 42 / 11 | 7; none | 744 |
| 147: `h-16-2001-patriots-0.iff` | 2001 / Tom Brady | 72 | 0 / 2 / 0 | 22; none | 731 |
| 149: `h-17-1991-saints-4.iff` | 1980 / Archie Manning | 57 | 2 / 53 / 0 | 6; none | 737 |
| 153: `h-18-1990-giants-2.iff` | 1990 / Jeff Hostetler | 52 | 3 / 31 / 21 | 14; none | 775 |
| 154: `h-18-2003-giants-0.iff` | 2002 / Kerry Collins | 66 | 0 / 0 / 1 | 23; none | 759 |
| 155: `h-19-1968-jets-4.iff` | 1968 / Joe Namath | 46 | 8 / 52 / 0 | 1; none | 719 |
| 157: `h-20-1967-raiders-1.iff` | 1968 / Daryle Lamonica | 49 | 5 / 52 / 1 | 1; 3 | 708 |
| 158: `h-20-1976-raiders-0.iff` | 1974 / Ken Stabler | 49 | 6 / 51 / 2 | 4; none | 717 |
| 159: `h-20-1983-raiders-0.iff` | 1983 / Jim Plunkett | 56 | 0 / 52 / 0 | 9; none | 747 |
| 162: `h-21-2004-eagles-0.iff` | 2003 / Donovan McNabb | 61 | 0 / 0 / 0 | 24; none | 604 |
| 163: `h-22-1975-steelers-1.iff` | 1972 / Terry Bradshaw | 49 | 6 / 52 / 1 | 3; none | 702 |
| 167: `h-23-1999-rams-2.iff` | 1999 / Kurt Warner | 67 | 0 / 1 / 0 | 21; 22 | 847 |
| 169: `h-24-1980-chargers-4.iff` | 1981 / Dan Fouts | 56 | 4 / 53 / 0 | 7; none | 745 |
| 171: `h-25-1981-49ers-3.iff` | 1981 / Joe Montana | 55 | 0 / 42 / 10 | 8; 6 | 725 |
| 172: `h-25-1989-49ers-3.iff` | 1988 / Joe Montana | 60 | 0 / 26 / 24 | 13; 11 | 739 |
| 174: `h-25-2003-49ers-0.iff` | 2002 / Jeff Garcia | 66 | 0 / 0 / 0 | 23; none | 747 |
| 177: `h-27-1979-buccaneers-3.iff` | 1987 / Steve DeBerg | 110 | 0 / 28 / 25 | 12; none | 762 |
| 181: `h-28-1979-oilers-2.iff` | 1991 / Warren Moon | 56 | 5 / 43 / 0 | 15; 17 | 763 |
| 182: `h-28-1999-titans-0.iff` | 1999 / Steve McNair | 62 | 0 / 0 / 0 | 21; none | 775 |
| 183: `h-29-1982-redskins-2.iff` | 1983 / Joe Theismann | 53 | 3 / 51 / 1 | 9; 5 | 735 |
| 187: `h-30-1986-browns-1.iff` | 1986 / Bernie Kosar | 53 | 3 / 53 / 0 | 10; none | 744 |

## PROVED writer behavior and integration contract

Owner: [nfl2k5_espn25_rosters.py](mod_editor/core/nfl2k5_espn25_rosters.py).
`REQUESTS = ()`. `status(resources)` and `apply(resources) -> (mapping, receipt)`
operate on a complete mapping of 35 whole wrapped resource spans. An executable
is not that mapping. There is no executable-owner tuple, allocator request,
cave, reservation change, executable digest update, save writer or new GUI panel.
The two existing XBE gates remain unchanged and pass their full owner unions.

The pinned manifest and every CSV hash are revalidated on every public operation,
including repeated checks in one process. Missing, changed or mixed datasets do
not use stale cached values. Each complete source resource must match either its
retail hash or its exact installed hash, and the whole set must be uniformly
retail or uniformly installed. Missing, foreign and mixed sets refuse before
compiling or writing. A compile failure in the 35th resource leaves the private
image identical. Replay returns the identical mapping with zero changes.

The existing string-pool allocator first reuses a known live allocation to release
old name blocks, then assigns the supplied names through the existing CSV/name
writer. It never claims padding or appends storage. Compilation compares every
changed byte against the allowed name-pool, name-pointer, jersey and college
fields, checks all other player bits, and re-decodes the team pointer order.
Wrappers are identical; sizes stay 7,200..8,032 bytes, totaling **263,648 bytes**.
Compressed resources and altered wrapper sizes refuse. There is no recompression
or changed sibling wrapper, including the SITU collection's other resources.

`read_resources` resolves actual archive entries and XDVDFS placement through the
existing `OuterImage`, including relocated packs and resources crossing a pack
boundary. It validates all 75 historical descriptors, the 25 title/date/name/year
bindings and the main college strings. `image_status` returns retail/applied/
foreign; edited narrative text alone may coexist, while a changed historic roster,
title/date/binding or college/descriptor identity refuses. Current-team labels and
current-player edits compose in either order and are tested. Existing One-pool
positions reclassifies historical positions and conflicts; protected Build
preflight must refuse it before making the image copy. A pending manual historic
roster/scenario plan must likewise be resolved in preview, not overwritten late.

`apply_to_image` accepts only a caller-owned disposable image, preflights the
complete transaction, rechecks the archive/resource snapshots, writes the fixed
spans, checks all reads and closes its handles. It is not itself a source-copy or
power-loss transaction. Its caller discards the private image on any I/O failure.
`build_image` is the copy-first API: it compiles before copying, refuses existing
targets, requires more than 100 GiB free after the copy, stages the image in a
temporary sibling directory, checks source identity/size/mtime and publishes with
`os.replace`. Optional `receipt_path` stages and closes the complete JSON receipt
before image publication; missing receipt directories fail before the copy.
Ordinary receipt/image-publication failures clean the stage and any just-published
receipt. A process or power loss between the two replacements can leave the
receipt alone; no two-file power-loss atomicity is claimed. The code introduces
no raw `os.open`; the existing archive owner uses `O_BINARY` and seek fallbacks.

The direct command is available now:

```sh
python3 -m mod_editor.core.nfl2k5_espn25_rosters validate-dataset
python3 -m mod_editor.core.nfl2k5_espn25_rosters status source.iso
python3 -m mod_editor.core.nfl2k5_espn25_rosters build source.iso historic.iso --receipt historic-receipt.json
```

The requested caption is **Historic moments: real rosters** (30 characters).
The help contains Retail, Patch and EXPERIMENTAL / UNWITNESSED and discloses
unknown starters/numbers, nearby-season fillers, shared teams and the retail
position-layout requirement. The release decision is **False in Basic, Advanced
and Experimental**, with explicit opt-in. All 25 bounded loading traces pass the
brief's necessary load condition, but that is insufficient evidence to default
on a profile with these known historical gaps. The brief's conditional preset
language is resolved conservatively and documented here.

[WIRING.md](WIRING.md#r64-espn-25th-real-rosters-2026-09-07) spells out the
dispatcher keyword and no-XBE-tuple decision; four status dictionaries; BuildPlan,
recipe/preset/source availability, data-only selection and final resource pass;
PATCHES/NEEDS_IMAGE and Build `_option`; every exact CSV/source allowlist line;
runtime closure and the schema-valid capability object. Shared protected files,
other GUI panels, registry contents and cave manifest were not edited. No full
protected Build, recipe, release-package or kickoff-plus-data integration result
is claimed before that handoff is applied.

## Original PROVED receipts, tests and their limits

Final dataset SHA-256:
`66ab419ad9fa3388b2749526f57b0d7b5a1d4c631560230dd6635457e97e6406`.
The complete patch changes **25,913 bytes in 23,730 exact contiguous spans** across
35 resources; archive growth is zero and `xbe_changed` is false. Every relative
offset, before/after hex span and resource hash is recorded. Applying those
receipts forward reconstructs the output and applying them backward reconstructs
the input in the standalone test. Replay has zero changed bytes and empty span
lists for every resource.

| Artifact | What it establishes |
| --- | --- |
| [Resource receipt](docs/mod_editor/nfl2k5_espn25_resource_receipt.json) | Actual retail slices to exact generated resource bytes; every changed span |
| [Replay receipt](docs/mod_editor/nfl2k5_espn25_replay_receipt.json) | Complete installed profile, zero byte changes |
| [Image receipt](docs/mod_editor/nfl2k5_espn25_image_receipt.json) | Real resource slices written through a 2,295,808-byte synthetic XISO with a split resource and moved pack extents |
| [Acceptance evidence](docs/mod_editor/nfl2k5_espn25_acceptance.json) | Whole original XISO hash before/after, source/extraction agreement, actual read-only locations, all non-owned synthetic image bytes unchanged and fixture disposal |
| [Native receipt](docs/mod_editor/nfl2k5_espn25_native_receipt.json) | All 25 selected moments, 50 archive requests, 2,650 imported player instances and scalar setup |

The **6,300,499,968-byte original XISO was only read**. Streaming SHA-256 before
and after acceptance was identical:
`7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`.
The image's executable equals the extraction's executable:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
All 75 historic resources plus main ROST and SITU retain their source hashes.
The synthetic writer proof compares **every image byte**, including the unchanged
synthetic executable, main ROST, whole SITU/siblings, unused 40 historic resources,
archive metadata, directories, gaps and other bytes. Actual source locations in
the acceptance JSON are read-only measurements, not claims that a full-size
output disc was built or tested.

The native harness executes the pinned retail `20CB30` selection, historic lookup
and filename formatter, `C1030` import/allocation and relocators, SITU selection
copy and scalar setup. Each moment imports two distinct teams with 53 distinct
player pointers each. Tests compare names, position/number, all clamped rating/
style bytes, selected appearance/depth fields, skin and college pointers to the
generated resource, and compare copied SITU records, scores, timeouts, quarter,
clock and down against the retail data. Calls have a 2,000,000-instruction budget.
Archive open/wait/find/release, controller selection, weather, spatial/model
callbacks, clock start/stop and presentation boundaries are explicit substitutes.
There is no rendered play, physical console or console emulator, audio, screen,
full-game formation execution, completion/reward proof or played witness here.

Final commands were plain standalone unittest invocations. Optional retail,
Unicorn and Capstone absence is handled by precise evidence skips; the completed
run below had **no skips** in either feature suite or either XBE gate.

| Command | Final result | Elapsed / peak resident memory |
| --- | --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_espn25_rosters.py` | PASS, 21 tests | 30.91 s / 151,728 KiB |
| `ESPN25_NATIVE_RECEIPT=docs/mod_editor/nfl2k5_espn25_native_receipt.json python3 tests/mod_editor/test_nfl2k5_espn25_rosters_native.py` | PASS, 1 test with 25 moment subtests, 2,650 player checks | 36.00 s / 105,112 KiB |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | PASS, 83 tests, unchanged complete owner union | 343.05 s / 292,476 KiB |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | PASS, 99 tests, unchanged complete owner union | 438.19 s / 507,348 KiB |
| `python3 tools/nfl2k5_espn25_rosters_from_nflverse.py --check` | PASS, 35 CSVs, manifest and both 75-resource inventories byte-identical | 8.44 s / 153,780 KiB |
| `python3 -m mod_editor.core.nfl2k5_espn25_rosters validate-dataset` | PASS, 35 resources, 1,855 players, 25 moments, opt-in | Bounded data reads |
| `python3 -m mod_editor.core.nfl2k5_espn25_rosters status <user-retail-xiso>` | PASS, retail | Read-only |
| `python3 .scratch/acceptance.py` | PASS, exact resource/image/replay receipts, original XISO unchanged, fixture deleted | 17.59 s / 135,596 KiB |
| `python3 -m mod_editor.capabilities.validate_registry --registry .scratch/espn25_registry_candidate.json --skip-file-checks` | PASS, merged 112-capability schema | All new entry paths and command modules also checked strictly by feature test |
| Full merged registry with `check_files=True` | BLOCKED by existing missing `docs/research/apf_audio.md` in capability 0 | No validator relaxation or fabricated research file |
| `git diff --check` | PASS | Explicit feature scope |

The 21-test feature suite covers dataset/identity provenance, all 75 codec round
trips, all 35 imports, positions/ratings/appearance/wrappers, college indices,
name-pool exhaustion, every mixed/foreign/missing transaction position, complete
span reconstruction, exact replay, the late-compile failure path, changed
context refusal, split resources, closed-handle replacement, Windows positional
I/O fallbacks, both orders with current-player/team-name edits, minimum free
space and receipt/copy publication failures. Windows behavior is exercised on
Linux with the existing lock tracker and seek fallbacks; native Windows/macOS CI
was not run. The full runtime/release gate awaits protected integration.

On resumption, the first validation attempts correctly failed because the
interrupted run had regenerated the dataset at 18:25 after its earlier tests
without updating the owner pin. Deterministic regeneration reproduced the final
files exactly before the pin was corrected. All results and receipts above were
then rerun against the final `66ab419...` dataset. Earlier scratch logs/receipts
with `d61c7c9...` and 25,906 changed bytes are superseded; they are not the shipped
evidence. The cache was also removed so a long-lived Studio check detects a later
missing/modified manifest or CSV. No failing test was reclassified as a skip.

## Original witness list and known gaps (see Exact lineups)

After the protected handoff is integrated, build a disposable disc with this
option explicitly selected and One-pool positions off. First use the same
otherwise-known configuration as the kickoff check. Keep the source and a copy
of the exact receipt so a lineup defect can be tied to the selected dataset.

For **each of the 25 rows in the per-moment table**, record pass/fail and notes:

1. Enter that menu row, load through to the field, and confirm both historical
   teams load without freezing or missing players. Re-enter it after another
   moment, especially a moment sharing one of its files.
2. Compare on-field names and numbers for both teams with the corresponding
   generated CSV. Check the pause-menu roster and depth chart across all 53
   players, including both lines, linebackers, nickel/dime, slot receivers,
   tight ends/fullbacks, kickers/punters and returners. Record unknown/inferred
   numbers as unresolved historical data, even if rendering matches the CSV.
3. Check QB1 and the moment's principal receiver/runner/returner or kicker at
   the actual starting state. Verify which eleven appear for that formation;
   the season-rank inference and intact pointer order do not establish that
   eleven. Flag the 12 shared-season conflicts before evaluating accuracy.
4. Run the intended offensive and defensive situation, substitutions and
   special-teams transition. Confirm formations fill, legal snaps occur,
   ball/clock/down/score/timeouts are sensible and the game can finish the
   scenario. Check success/failure, completion mark, reward and later re-entry;
   none of those full-play outcomes is proved by the bounded importer trace.
5. Repeat representative moments with the kickoff options intended for the
   release. Confirm returners, coverage players, field behavior and pause roster
   still agree. Also check an ordinary current-team game and a historic
   exhibition sharing a changed file, where the roster change is expected.

This checklist does not turn season membership, a guessed starter, a nearby-year
number, a different-year shared team or retail slot appearance into historical
proof. Exact game starters, injuries, substitutions and snap-specific players
need additional game-level evidence that was not supplied. Even perfect loading
cannot resolve the missing data or the fixed shared-roster limitation.

## Original delivery and resource discipline

No network, GUI display, audio, console emulator, other-worktree edit, source
mutation or push was performed. Existing ASTRA report summaries, the RC85
changelog, relevant roster/storage/allocator/Windows-handle reports and the
parallel scenario research informed the implementation; no protected mechanism
was duplicated. Root free space stayed about 101 GiB. A full disc copy would
violate the chosen 100 GiB post-copy floor, so none was made. Every synthetic
image/pack lives under `TemporaryDirectory` and is deleted on exit. Full source
hashing uses 1 MiB stream chunks. The largest measured test process is 507,348
KiB, below the 2 GiB limit. Scratch contains only scripts, logs, JSON and notes,
well below 200 MiB, with no retained disc or pack.

The explicit commit includes this report, the appended WIRING handoff, the new
owner and generator, the 35 CSVs plus manifest, the two standalone tests and
native helper, inventory CSV/JSON, capability object and five evidence receipts.
`ASTRA_BRIEF.md`, `.scratch/` and the supplied raw `inputs/` remain uncommitted.
The public runtime allowlist handoff ships source and attributed generated CSV
recipes; decoded retail inventories and exact research receipts stay repository
evidence. No binary ROST, retail executable, save or disc is distributed. The
nflverse license covers its supplied data, not the user's retail game data or
the preserved retail profiles. No new third-party runtime dependency is needed.

The final explicit-path staging attempt failed with `Read-only file system` at
the shared worktree `index.lock`. An earlier single-file staging probe succeeded;
the original worktree therefore retains its files and that staged owner. The
brief's authorized fallback is `.scratch/espn25-rosters.bundle`: a commit on the
same named branch, based on the original HEAD, built in a temporary local shared
object repository with exactly the 51 listed feature paths. Its tree is checked
against every delivered file and its changed-path list, and the bundle is
verified. The original branch's HEAD is not advanced by the fallback. No remote
fetch or push is used.

The bundle requires base commit
`76434d6108a25ca7deac0160fb05f717badd7bd0`. In a clean coordinating checkout with
that base available, inspect with `git bundle verify <espn25-rosters.bundle>` and
import with `git fetch <espn25-rosters.bundle> refs/heads/astra/r64-espn25-rosters`,
then cherry-pick the fetched commit through the normal integration process.
The bundle head is also recorded in `.scratch/espn25_delivery.json`; the brief,
raw inputs, scratch scripts and scratch repository are not in its commit.
