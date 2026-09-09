# ASTRA_REPORT — beta-63.1: Franchise Schedule "Apply to this game" refused on a real playoff save

Branch `astra/hf63-franchise-schedule` (from tag `beta-63`, 9c17c538).  Report by the agent the brief calls
Astra (Claude Fable 5.1 in this worktree).  No push, no emulator, no GUI display; Qt ran offscreen.

Commits (explicit paths, newest last):

| commit | what |
|---|---|
| `81123c90` | Regression test (red): `tests/mod_editor/test_nfl2k5_franchise_schedule_college.py` |
| `b0a49c68` | Core: `nfl2k5_save_rost.py`, `nfl2k5_practice_squad.py`, `nfl2k5_franchise_save.py`, `providers.py` (repin) |
| `c4181fa8` | Smallest change in the two protected panels + `WIRING.md` section + the write-path regression check |
| `3e5074ea` | Core: the free-agent refusal names its entry (`nfl2k5_save_rost.py`, `providers.py` repin) |

Branch diff against `beta-63`: 8 files, +381 / −44 (`WIRING.md` gained a 47-line section at the top of the
existing ledger; nothing else in it moved).

## 1. The report

BigTimeEmpire, #2k5-bugs 2026-09-08 19:16 ("Was trying to edit the kickoff time in my playoff franchise and
I got this error"), screenshot `discord-dump-2026-09-09/shots/2k5-bugs_021.png`: ★ Rosters → Franchise →
Schedule, header `2025 (season 22 – index 21), postseason week 17/22, user team(s) SF, CHI, … MIN (all 32),
cap $80.5M, 256/268 grid games played, 0 on IR`, "All postseason · 12 games, 0 played", Away HOU at Home PIT,
date 1/8, kick-off 8:00, **Apply to this game** → both status lines (the Franchise page's and the roster
page's) read

    Refused: no supported ROST: unsupported ROST version 593952; player college is not a college record

(The brief transcribed the number as 593352 / 0x90E48; those two do not even agree with each other, and §3
shows the word is 593952 = 0x91020.)  It is the tester's first season (cap still $80,500 = the 2004 value;
21 seasons would have compounded it), all 32 teams user-controlled, first postseason.

## 2. Reproduction (offline, exact message)

No real save with the anomaly is available (the tester posted a screenshot only).  All four real franchise
saves on this machine pass the codec: the three hub fixtures (`f0`, `f1`, `256B40374FD6-Franchise1`) and the
`MyNFL1` save read straight out of Noah's xemu `xbox_hdd.qcow2` (extracted read-only into the scratchpad
with `tools/nfl2k5_xemu_saves.py`, never into the repo).  On every one of them the studio's `load_save` →
`document.to_body()` round trip is byte-identical (0 differing bytes), `validate_save` passes and a kickoff
edit applies — so the studio does not manufacture the anomaly; the tester's save carries it.

The failure is reproduced with the core tests' synthetic franchise save plus one primary player whose
college pointer is moved 4 bytes past the last college record (inside the arena, off the table), loaded in
the real `RosterEditorPanel` offscreen, then `page.edit_game(0, 1, hour=8, minute=30)` (what **Apply to this
game** calls):

    colleges 5 0xaa38 player0 0xb288 college -> 0xaa38
    decode refusal: no supported ROST: unsupported ROST version 593952; player college is not a college record
    load_save True
    active True | status before: Franchise save: 2011 (season 8 = index 7), regular season week 3/17, ...
    edit_game -> False
    franchise status: Refused: no supported ROST: unsupported ROST version 593952; player college is not a college record
    roster status:    Refused: no supported ROST: unsupported ROST version 593952; player college is not a college record

Same text, same two lines as the screenshot.  The regression test file was committed first and run against
the unfixed tree (§5, "red").

## 3. Root cause, file:line (line numbers as of `beta-63`)

The chain behind the message, innermost last:

1. `mod_editor/gui/roster_editor_panel_qt.py:1487` — `RosterEditorPanel._franchise_edit` (the studio path;
   `FranchisePanel.push` delegates to it) ran `validate_save(candidate.to_bytes())` after **every** franchise
   edit, including a `"game"` edit whose only write is the 8-byte schedule cell in the season block
   (`0x917EA + …`).  `mod_editor/gui/franchise_panel_qt.py:636/659/702` (`_rebuild`, `push`, `redo`) did the
   same for the standalone page.
2. `mod_editor/core/nfl2k5_practice_squad.py:308-313` `validate_save` → `:186` `validate_roster` →
   `nfl2k5_save_rost.decode(payload)`: the practice-squad ownership validator decodes the whole 720,044-byte
   save with the strict codec.
3. `mod_editor/core/nfl2k5_save_rost.py:204` — `_require(college is None or college in college_records,
   'player college is not a college record')`: one player's college pointer that stays inside the arena but
   does not land on one of the `count` college records refused the whole ROST.  The game never checks this
   pointer: the player card dereferences it for the `COLLEGE:` line and the team exporter maps an unknown
   target to college 0 (`FUN_00242190`, read-only pseudo-C under `/media/noah/Storage/for codex 1.0/research/
   functions/nfl2k5/pseudo_c/shard_009728_010239.c`); every in-game writer (`FUN_000e6780` rookie roll,
   Create Player `FUN_002421f0`, team import `0xC1030`) is index-bounded (`table + i*8` with `i < count`, else 0), so the
   pointer most plausibly came in with the modded disc roster the franchise was started from — that cannot be
   proved without the tester's save (§7).  The studio's own roster parser already tolerates it:
   `mod_editor/core/nfl2k5_roster_records.py:1587` reads such a player as "no college", which is why the
   roster page and the Franchise page loaded and only the edit was refused.
4. `mod_editor/core/nfl2k5_save_rost.py:327-331, 337` — the candidate scanner tried every `ROST` in the first
   64 KiB as an inner header, including the 0x20-byte **outer wrapper's** magic at 0x2E0, whose length word
   sits where a preamble keeps its version.  That candidate always fails with `unsupported ROST version
   <declared length>` and its text is joined in front of the real refusal (`:357`).
5. `mod_editor/core/nfl2k5_franchise_save.py:409` — `FranchiseSave.write()` ran `validate_save(payload)`
   unconditionally, so even with the edit gate removed the copy could not have been written.

**What "version 593352" is.**  Not a ROST version.  It is the outer wrapper's declared resource length at
file 0x2E4: `0x91020 = 593,952` on every 720,044-byte franchise save (all four real saves here carry exactly
that word; the regression test pins it).  `FranchiseSave.__init__` (`nfl2k5_franchise_save.py:363-368`)
refuses any other value, and the Franchise tab only appears when that constructor succeeds — so the tester's
save carried 593952 too, and the screenshot's small type was read as 593352.  The pinned layout (wrapper
0x2E0 declared 0x91020, preamble 0x300 version 0, root 0x320, arena 0x91000) was intact; nothing about the
pin had to be widened, and it was not.

## 4. The fix

**Core (`b0a49c68`)**

- `nfl2k5_save_rost.SaveRost._parse`: an in-arena college pointer that is off the college table is recorded
  in `SaveRost.unresolved_colleges: {(pool, index): target}` (also `summary()['unresolved_colleges']`), not
  refused.  `to_bytes()` still copies the bytes verbatim and `edit_player` still refuses pointer edits, so
  nothing is lost or rewritten.  A pointer that leaves the arena is refused as before.
- Every per-player refusal (college pointer, first/last name strings, history stream) is prefixed with
  `<pool> player <index> at 0x<offset>:` — e.g. `primary player 0 at 0xB288: history stream outside used
  pool` — so the next report names the record.  (The history loop moved into `_read_history`; same checks,
  same counts.)
- `decode()`: a `ROST` whose bytes at +0x2C are also `ROST` is the outer wrapper of the preamble at +0x20
  (which the same scan finds); it is no longer tried as a header.  A real version mismatch still reads
  `unsupported ROST version N`.  Acceptance is unchanged (a wrapper candidate could never pass).
- `nfl2k5_practice_squad.validate_save_edit(before, after, **options)`: `validate_save(after)` unless the
  ROST resource (`0x2E0..arena_end`) and the injured-reserve table are byte-identical between the two, in
  which case it returns `None` — a schedule / year / cap / user-control edit cannot change ownership.
- `FranchiseSave.write()` validates through `validate_save_edit(self.original, payload)`: the codec runs on
  the way out only when roster state changed since the load.
- `providers.py`: self-integrity pins for the three modules re-synced (`python3 packaging/repin.py --apply`,
  3 updates).  **Claude: manifest regeneration needed** per the pinned-writer rule.

**Protected panels (`c4181fa8`, the smallest change, described in `WIRING.md`)**

The four call sites (`roster_editor_panel_qt._franchise_edit`; `franchise_panel_qt._rebuild/push/redo`)
pass the pre-edit bytes to `validate_save_edit(before, after)` instead of calling `validate_save(after)`.
No widget, label, layout, preset or copy text changed.  Arena edits (IR, promote/demote, coach fields,
roster-page membership) are validated exactly as before.

Not done, deliberately: no new UI for unresolved colleges, no preset change, no change to
`nfl2k5_roster_records.save_document` (the roster-save write path; it now passes for the college case via the
codec change), no widening of the version pin.

## 5. Tests

Command form: `cd <worktree> && PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/<file>.py`.

**Red, before the fix** (`81123c90` checked out on the beta-63 tree):

    ERROR: test_an_off_table_college_pointer_is_recorded_not_refused
    mod_editor.core.nfl2k5_save_rost.SaveRostError: no supported ROST: unsupported ROST version 593952; player college is not a college record
    FAIL: test_apply_to_this_game_works_on_a_save_with_an_unresolved_college
    AssertionError: False is not true : Refused: no supported ROST: unsupported ROST version 593952; player college is not a college record
    FAIL: test_a_schedule_edit_does_not_depend_on_the_roster_codec_but_an_ir_move_still_does
    AssertionError: False is not true : Refused: no supported ROST: unsupported ROST version 593952; history stream outside used pool
    FAIL: test_the_wrapper_length_is_not_reported_as_a_version
    AssertionError: '593952' unexpectedly found in 'no supported ROST: unsupported ROST version 593952; primary players and teams are required'
    (+ the naming and validate_save_edit cases)
    Ran 8 tests in 0.638s
    FAILED (failures=5, errors=5)

**Green, after** — `tests/mod_editor/test_nfl2k5_franchise_schedule_college.py` (8 tests: codec records the
pointer and round-trips; out-of-arena pointer still refused naming `primary player 1`; the wrapper word is
never reported as a version while `unsupported ROST version 5` still is; refusals name the player;
`validate_save_edit` skips for season-block-only edits and validates arena/IR changes; the real fixtures
carry 593952 and no unresolved college; the panel applies the kickoff edit, Swap home/away and writes the
re-signed copy with only the schedule cell changed; on a save the codec still refuses, schedule/cap/control
edits apply and the copy is written while an IR move is refused naming the record):

    $ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_franchise_schedule_college.py
    Ran 8 tests in 2.761s
    OK
    $ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_save_rost.py
    Ran 9 tests in 4.208s
    OK
    $ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_practice_squad.py
    Ran 27 tests in 36.915s
    OK
    $ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_franchise_save.py
    Ran 13 tests in 2.216s
    OK
    $ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_franchise_panel_qt.py
    Ran 16 tests in 45.721s
    OK
    $ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_roster_editor_panel_franchise.py
    Ran 2 tests in 0.664s
    OK
    $ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_roster_editor_panel_qt.py
    Ran 50 tests in 10.627s
    OK
    $ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_providers.py
    Ran 33 tests in 5.034s
    OK

**Every test file that imports a changed module** (`nfl2k5_save_rost`, `nfl2k5_practice_squad`,
`nfl2k5_franchise_save`, `franchise_panel_qt`, `roster_editor_panel_qt`, `providers`), each run standalone
with plain `python3` and `PYTHONPATH=<worktree>`, `QT_QPA_PLATFORM=offscreen` (the machine was under a load
average of ~36 from sibling hotfix sessions, hence the wall times):

    test_franchise_panel_qt                              rc=0 Ran 16 tests in 45.721s OK
    test_gameplay_patches_panel_qt                       rc=0 Ran 1 test in 0.113s OK
    test_nfl2k5_abilities_v2                             rc=0 Ran 15 tests in 46.314s OK
    test_nfl2k5_depth_locks                              rc=0 Ran 22 tests in 96.578s OK
    test_nfl2k5_espn25_integration_qt                    rc=0 Ran 13 tests in 16.922s OK
    test_nfl2k5_franchise_2026                           rc=0 Ran 20 tests in 7.753s OK
    test_nfl2k5_franchise_2026_runtime                   rc=0 Ran 10 tests in 87.878s OK
    test_nfl2k5_franchise_save                           rc=0 Ran 13 tests in 2.216s OK
    test_nfl2k5_franchise_schedule_college               rc=0 Ran 8 tests in 2.761s OK
    test_nfl2k5_my_career                                rc=0 Ran 13 tests in 19.353s OK
    test_nfl2k5_my_career_control                        rc=0 Ran 2 tests in 13.431s OK
    test_nfl2k5_my_career_draft                          rc=124
    test_nfl2k5_my_career_inline                         rc=0 Ran 8 tests in 11.225s OK
    test_nfl2k5_my_career_mode_audit                     rc=0 Ran 6 tests in 0.070s OK
    test_nfl2k5_my_career_mode_routes                    rc=0 Ran 7 tests in 3.936s OK
    test_nfl2k5_olb_row                                  rc=0 Ran 13 tests in 54.353s OK
    test_nfl2k5_player_star_draw                         rc=0 Ran 15 tests in 42.425s OK
    test_nfl2k5_playoff_editor                           rc=0 Ran 9 tests in 1.082s OK
    test_nfl2k5_practice_reserves                        rc=0 Ran 9 tests in 20.141s OK
    test_nfl2k5_practice_squad                           rc=0 Ran 27 tests in 36.915s OK
    test_nfl2k5_practice_squad_screen                    rc=0 Ran 10 tests in 389.995s OK
    test_nfl2k5_save_rost                                rc=0 Ran 9 tests in 4.208s OK
    test_nfl2k5_season_cap_saves                         rc=0 Ran 7 tests in 0.205s OK
    test_nfl2k5_weekly_prep                              rc=0 Ran 11 tests in 19.110s OK
    test_nfl2k5_weekly_prep_unicorn                      rc=0 Ran 17 tests in 21.001s OK
    test_playoff_editor_panel_qt                         rc=0 Ran 6 tests in 19.678s OK
    test_product_catalog                                 rc=0 Ran 9 tests in 0.038s OK
    test_providers                                       rc=0 Ran 33 tests in 5.034s OK
    test_roster_editor_panel_franchise                   rc=0 Ran 2 tests in 0.664s OK
    test_roster_editor_panel_qt                          rc=0 Ran 50 tests in 10.627s OK
    test_roster_save_to_disc                             rc=0 Ran 21 tests in 18.333s OK
    test_rosters_data_qt                                 rc=0 Ran 6 tests in 0.924s OK
    test_rosters_reserves_abilities                      rc=0 Ran 13 tests in 11.237s OK
    test_rosters_reserves_abilities_qt                   rc=0 Ran 7 tests in 3.200s OK
    test_rosters_salary_native                           rc=0 Ran 1 test in 0.265s OK
    test_save_roster_import                              rc=0 Ran 12 tests in 0.002s OK
    test_studio_shell_layout_qt                          rc=0 Ran 18 tests in 128.356s OK
    test_ux_open_disc_hook_qt                            rc=0 Ran 7 tests in 23.314s OK
    test_ux_rosters_words_qt                             rc=0 Ran 4 tests in 0.229s OK

`test_nfl2k5_my_career_draft` (rc=124) is the Unicorn full-draft emulation; it hit my harness's 25-minute
per-file limit under that load.  It exercises the practice-squad **XBE** owner (`ps.apply`, `ps.SYMBOLS`),
not the codec or the validator this hotfix touches; it was re-run alone afterwards — see the note at the end
of this section.

Portability gates: `test_shipped_tools_posix_only` (13 OK), `test_directory_publishes_are_portable` (5 OK),
`test_local_windows_ci` (51 OK), `test_caller_windows_pins` (19 OK).  The hotfix adds no file I/O of its own;
the test uses `tempfile` and the existing container helper.

Not run: the two XBE gates (`test_xbe_patch_memory_writes`, `test_xbe_patch_cave_references`) — no game-code
writer changed; the release gate (`check_2k5_mod_studio_release.py`) needs the gitignored
`reports/assets/*.json` inputs that are absent here.  `python3 packaging/repin.py --apply` was run for the
three pinned core modules (providers.py pins updated; `test_providers` green).

UNICORN_RERUN_PLACEHOLDER

## 6. What Noah must witness (nothing in-game is proved here)

1. On a real franchise save (his own, or any tester's), ★ Rosters → Franchise → Schedule → pick a game →
   change the kick-off hour/minute → **Apply to this game**: the status line must show the edit label (e.g.
   `Divisional game 1: hour 4 → 8`), not a refusal; **Save a copy**, load it in xemu, open the franchise
   schedule and check the kick-off time (the schedule cell writer itself has been PROVED since beta-60; this
   hotfix changes only what gates it).
2. BigTimeEmpire's save is the only one known to carry the college anomaly.  Ask him for the
   `SAVEGAME.DAT` + `EXTRA` (or the whole `UDATA/53450030/<uid>` folder) and (a) confirm beta-63.1 applies
   the kickoff edit on it, (b) note which player `SaveRost(...).unresolved_colleges` names, (c) check that
   player's COLLEGE line in the game's player card — that tells us where the pointer came from (§7).
3. An IR move on a save with a genuine structural problem now refuses with the player named; if a tester
   reports such a line, the record is identified without guessing.

## 7. Open question, stated honestly

The origin of the off-table college pointer is not proved.  Facts: the game's own writers are bounded
(§3.3); the studio's writers (`set_college`, CSV import, Finn `.PlayerData` restore, save-roster-to-disc)
resolve colleges through the table; the four real saves here have none.  The most plausible source is the
modded disc roster the tester's franchise was started from (community rosters pass through several
third-party tools; the tester is also the one who pinned the PS2 port build).  The hotfix makes the studio
tolerate what the game tolerates and reports the record precisely, which is the right behaviour whatever the
source; the tester's file would settle it.
