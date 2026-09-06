# r62 Franchise playoff editor correction

2026-09-06. **EXPERIMENTAL / UNWITNESSED.** Base
`04a398c8c525800e020f3a6b46a35f027dd90b3f`, branch
`astra/r62-franchise-playoff-editor`. No push, network, emulator, graphical
display, audio or disc build was used. Qt ran offscreen. Preserved inputs
were read only; signed output copies lived in automatically removed temporary
directories. No gameplay acceptance is claimed.

## Delivered

The Franchise schedule now recognizes the shipped 17/18-week save layouts,
lists every existing postseason game with its round, and edits dates/kickoff
times even before participants qualify. **All postseason** is the initial
schedule view for postseason saves and completed saves with postseason records.
Individual week/round filters remain available. Every table item retains its
physical `(row, slot)` identity through filtering, edits, undo and redo.

Undecided participants display **To be decided** in both the table and the
disabled team selector. Their date and time controls work. A played game
immediately displays **This game has been played** and explains the existing
**Allow editing played games** override. The checkbox resets on load and does
not discard a pending date/time change when checked. Scores remain read-only.

The codec validates the whole proposed edit before replacing exactly one
eight-byte record. Failed validation cannot partially modify a direct codec
call. Dates/times do not change participants, qualification flags, score
records, calendar year bytes, adjacent games or other franchise data.

Changed product files: `mod_editor/core/nfl2k5_franchise_save.py`,
`mod_editor/gui/franchise_panel_qt.py`, and
`docs/mod_editor/franchise_save.md`. Two new standalone unittest files cover
the regression. No protected file or other GUI panel changed. No new imports
in the product, build option, runtime owner, resource or capability surface
was introduced, so no WIRING handoff is needed.

## Exact root causes and reproduction boundary

**PROVED, placeholder date/time refusal:** `FranchiseSave.set_game()` ended
every edit with an unconditional `home != away` check. The playoffs14 builder
copies scheduled records with zero team bytes until teams qualify. Its
`GAME_TABLE` explicitly creates divisional slots 1/3, both conference games
and the Super Bowl with neither participant known; divisional slots 0/2
start with only their home team. The two flag bytes, not the zero team value,
distinguish an undecided side from actual team 0. Consequently ordinary date
or time edits failed with `a team cannot play itself`. A home-only fixture
whose #1 seed is team 0 also reproduces that error. This is not a week guard
or a restriction on postseason dates.

Before-code execution on the synthetic 18-week/14-team bracket refused cells
`19/0`, `19/1`, `19/3`, `20/0`, `20/1`, `21/0` for that exact reason. The
17-week/12-team fixture refused `18/0`, `19/0`, `19/1`, `20/0`. These are
zero-based row/slot pairs. The #1 seed is deliberately team 0 in both fixtures.
Dates and kickoff bytes had already been changed before the exception in a
direct call. The panel's candidate/journal rollback prevented that partial
write from reaching its saved copy, making the user's edit appear to fail.

**PROVED, wrong round identity:** the codec's `ROW_NAMES` and panel's
`GRID_ROW_TITLES` always used retail rows 17..21. The shipped season-length
owner keeps the grid at 22 rows, puts Week 18 at row 17, shifts playoffs to
18..21, and drops the Pro Bowl. Before this fix, the 18-week fixture appeared
as follows. Counts come from actual bounded fixture records, not a presumed
four-game cap:

| Physical row | Before label | Actual contents / corrected label |
|---|---|---|
| 17 | Wild Card | 16 final regular-season games / Week 18 |
| 18 | Divisional | 6 Wild Card games |
| 19 | Conference | 4 Divisional games |
| 20 | Super Bowl | 2 Conference games |
| 21 | Pro Bowl | 1 Super Bowl |

All 13 playoff games were present across the old filters, but none were under
their proper round. There was no four-game limit in this reader and no
eight-byte record-stride shift for 14 teams. The initial filter was also
Week 1 for every stage except regular season, including stage 9. An empty
selection disabled date/time controls without a selection-specific notice.

**PROVED on a synthetic gap, not on a preserved real save:** `games()` used
`break` at the first type-7 filler. Replacing Wild Card slot 1 with a filler
while keeping existing slots 2..5 made the old reader show only slot 0.
The corrected reader shows slots `0,2,3,4,5`, preserving their identities and
scanning no farther than the 17 slots in that row. This removes a concrete
omission path in edited/sparse saves. It does not prove the game itself
produces such gaps.

**PROVED, played-game refusal on the real Lions save:** its 12 postseason
records are all type 3. The original played-game guard refused every date
and kickoff edit unless explicitly overridden. That behavior is retained;
the reason is now visible before Apply, alongside the selected game, and in
the row tooltips. Regular-season rows follow the same rule.

**HYPOTHESIS / unresolved attribution:** the supplied Discord image contains
BigTimeEmpire's text, without the affected save or editor screenshot. The
preserved real saves do not reproduce omitted records. Therefore this report
does not claim the particular Discord save's missing rows were located, or
that its exact symptom was witnessed. The placeholder refusal and shifted
labels are reproduced independently using the shipped layout/builder contract;
the filler omission is a separate synthetic regression.

## Preserved real-save inventory

Inputs are under `/home/noah/Desktop/2K5-8 Editors/save_fixtures/`, overridable
in tests with `NFL2K5_SAVE_FIXTURES`. Each is 720,044 bytes. SHA-256:

| Fixture | SAVEGAME.DAT SHA-256 | Postseason records |
|---|---|---|
| `f0` / `0B8506889D40` | `56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8` | 0 |
| `f1` / `0B8506889D40` | `255da39178695a69c01efad9237764cbbd88c63aa78cfe911c8e3b070b6215ed` | 0 |
| `256B40374FD6-Franchise1` | `0db746fe2c8ae2102fdd420863a5e5bcddec4b83ac3e234568824c337e4422a7` | 12 |

Both Finn variants are stage 8, week 0, regular-stage bound 17, year index 0,
with a 256-game template. Every one of the 85 cells in rows 17..21 is the
eight-byte filler `0700000000000000`: Wild Card 0, Divisional 0, Conference 0,
Super Bowl 0, Pro Bowl 0. Neither editor version omits an existing postseason
game there. Their no-op signed-copy round trips are byte-identical.

The Lions save is stage 1/substate 2, week 0, stage bound 1, year index 7,
with a 256-game template. Below is the exact physical/editor order. All
listed cells are played, all flags are `0x0101`, and all other postseason
cells are fillers. **Missing from the original list: none.** The old editor
required choosing these rounds individually; the new combined view lists
them together in this same order.

| Row/slot | File offset | Round | Away at home | Saved month/day | Kickoff | Exact eight bytes |
|---|---|---|---|---|---|---|
| 17/0 | `0x920F2` | Wild Card | OAK at JAX | 1/8 | 12:30 | `031016010800001e` |
| 17/1 | `0x920FA` | Wild Card | CLE at PIT | 1/8 | 4:05 | `031c050108000405` |
| 17/2 | `0x92102` | Wild Card | WAS at SF | 1/9 | 12:35 | `0300190109000023` |
| 17/3 | `0x9210A` | Wild Card | CHI at CAR | 1/9 | 4:15 | `031401010900040f` |
| 18/0 | `0x9217A` | Divisional | CLE at BUF | 1/15 | 12:35 | `030305010f000023` |
| 18/1 | `0x92182` | Divisional | OAK at DEN | 1/15 | 4:15 | `030416010f00040f` |
| 18/2 | `0x9218A` | Divisional | CHI at DET | 1/16 | 12:40 | `0312010110000028` |
| 18/3 | `0x92192` | Divisional | WAS at DAL | 1/16 | 4:15 | `030b19011000040f` |
| 19/0 | `0x92202` | Conference | DEN at BUF | 1/23 | 1:35 | `0303040117000123` |
| 19/1 | `0x9220A` | Conference | WAS at DET | 1/23 | 4:15 | `031219011700040f` |
| 20/0 | `0x9228A` | Super Bowl | BUF at DET | 1/30 | 4:00 | `031203011e000400` |
| 21/0 | `0x92312` | Pro Bowl | 33 at 32 | 2/6 | 4:00 | `0320210206000400` |

The last pair is the retail NFC/AFC Pro Bowl pair; this particular arena's
team abbreviations are `USER2`/`USER1`, which the panel preserves. Times above
use the existing editor's hour-byte presentation, where zero prints as 12;
no AM/PM or historical year is invented. The old postseason byte at +5 is
zero in these real records and is preserved rather than automatically redated.

## Synthetic 14-team inventory and layout decisions

`synthetic_postseason()` in the new core test builds a bounded franchise
using `nfl2k5_playoffs14.GAME_TABLE` and `CALENDAR_2026_14`, with the home/away
qualification flags emitted by that builder. It includes a 272-entry saved
template and 16 completed Week 18 records. These are constructed save bytes,
not a captured runtime save. The full 18-week postseason is:

| Row | Slots | Round | Saved dates and kickoffs, in slot order |
|---|---|---|---|
| 18 | 0..5 | Wild Card | Jan 16 4:30; Jan 16 8:15; Jan 17 1:00; Jan 17 4:30; Jan 17 8:15; Jan 18 8:15 |
| 19 | 0..3 | Divisional | Jan 23 4:30; Jan 23 8:15; Jan 24 3:00; Jan 24 6:30 |
| 20 | 0..1 | Conference | Jan 31 3:00; Jan 31 6:30 |
| 21 | 0 | Super Bowl | Feb 14 6:30 |

The year byte is 27 (2027) in this fixture. There is no Pro Bowl record and
no row 22. Separate fixtures cover all combinations of 17/18 regular weeks
and 12/14 playoff teams. In the 17-week cases the Pro Bowl occupies row 21.
The wild-card count never decides the record stride or limits enumeration.

Recognition priority is: an explicit 17/18 regular-stage bound; a bounded
256/272-record saved template; then the occupied tail (Pro Bowl participants
32/33, an occupied final NFL round, or counts incompatible with the retail
round at that position). An empty or ambiguous tail defaults to 17. The
configured display year is not used: a 2026 starting year can still use the
retail layout. Arbitrary custom schedules with conflicting evidence are not
certified. No future round is synthesized and no executable setting is guessed.

Only month/day/hour/minute are supplied by the panel for date/time edits.
The +5 byte used by the calendar engine for year minus 2000 remains untouched;
tests include 2027, 2100 and 2154. Bounds are unchanged from regular-season
editing: month 1..12, day 1..31, hour 0..12, minute 0..59. This fix does not
introduce calendar-date validation or an AM/PM model beyond the existing editor.
The calendar engine, playoffs14 owner and disc-template writer need no changes.

## Validation

All tests ran as standalone `python3 file.py` processes. Real fixture tests
executed here; they have precise per-fixture skips for machines without the
private saves. No test loaded a disc or archive pack into RAM. The existing
schedule smoke test reads only its 593,792-byte ROST span. New synthetic
save buffers are approximately 703 KiB; no disc images or real packs were built/copied.

| Exact command | Result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_playoff_editor.py` | 9 tests, OK, no skips |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_playoff_editor_panel_qt.py` | 6 tests, OK, no skips |
| `python3 tests/mod_editor/test_nfl2k5_franchise_save.py` | 13 tests, OK, no skips |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_franchise_panel_qt.py` | 16 tests, OK, no skips |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_roster_editor_panel_franchise.py` | 2 tests, OK, no skips |
| `python3 tests/mod_editor/test_nfl2k5_season_cap_saves.py` | 7 tests, OK, no skips |
| `python3 tests/nfl2k5_franchise_schedule_test.py` | 12 tests, OK, no skips |
| `git diff --check` and `git diff --cached --check` | PASS |

Total: **65 tests passed**. This is the relevant save/panel/calendar regression
set, not a claim of full application CI. The new tests independently compare
the complete written file against the allowed byte positions; verify every
listed postseason cell, placeholder and played notice; exercise sparse slots,
the final grid cell adjacent to scores, malformed edit atomicity, identity
through undo/redo, and signed copy/reload for real and synthetic saves.

Before-code observations and final test logs are under
`.scratch/playoff-editor/` and are excluded from the commit. The before-code
module was loaded from the pinned base with `git show`, without restoring or
writing another worktree. The prior Astra report inventory, RC85 changelog,
franchise-save documentation and shipped calendar/playoff owners supplied the
compatibility boundaries for this change.

## BigTimeEmpire / Noah witness list

1. Open a copy of the affected franchise in the fixed editor. On Schedule,
   choose **All postseason**. Record the build's regular-season length,
   current stage and every displayed round/count. A populated 14-team bracket
   should have six Wild Card, four Divisional, two Conference and one Super
   Bowl game. A 17-week retail bracket also has its saved Pro Bowl game.
2. Compare the editor with the game's Schedule/Results screen, including both
   extra Wild Card games. For an 18-week save, verify Week 18 is a regular
   week and that the championship is labelled Super Bowl, with no extra
   Pro Bowl manufactured. Record any disagreement with its teams and round.
3. Before later-round teams qualify, select each undecided Divisional and
   Conference game. Change its date and kickoff time, Apply, undo, redo,
   write a new signed copy and reopen it. Verify the values persist and
   undecided teams remain undecided. Repeat for a home-only game whose home
   team is the 49ers (team 0 in retail), if that matchup exists.
4. Select an already played Wild Card or Divisional game. Verify the notice
   appears immediately and Apply refuses until **Allow editing played games**
   is checked. On a disposable copy, enable it and repeat the date/time edit;
   verify scores, teams and the recorded winner remain unchanged on reload.
5. Load the edited copy in the matching game build. Confirm dates/kickoff
   display, play or simulate the next playoff game, advance to the next
   round, save and reload. Check that reseeding and later opponents still
   work. Repeat with the 2026 calendar through the championship. These live
   observations, including the game's acceptance of edited played dates,
   remain UNWITNESSED.

If BigTimeEmpire's specific save still differs, preserve the untouched save
and identify the exact row/teams and whether the record exists in the bounded
grid. The supplied screenshot alone cannot settle that outstanding attribution.

## Delivery

An initial explicit-path staging command succeeded, but final staging failed
with `Unable to create .../index.lock: Read-only file system` in the shared
Git metadata. Delivery therefore uses the authorized fallback: an isolated
Git directory under `.scratch/`, the pinned base as parent, and a commit
containing only the six explicit paths above. The bundle is
`.scratch/r62-franchise-playoff-editor.bundle`; edited files remain in this
worktree and the shared branch is not advanced. Its index may retain the
earlier partial staging; the bundle commit contains the complete final files.
`ASTRA_BRIEF.md`, the supplied Discord image and `.scratch/` are excluded from
the commit. Nothing is pushed.
