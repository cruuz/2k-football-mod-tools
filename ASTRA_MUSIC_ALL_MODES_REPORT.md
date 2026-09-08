# Music tier 4b: all named routing contracts and rebuilt-library validation

2026-09-06, branch `astra/r62-music-all-modes`, base `b7bac4f`.
**EXPERIMENTAL / UNWITNESSED.** No gameplay or audible output was witnessed.

## Delivered

The shared controller now handles native screen activation and the actual draft
entry. All 24 named context contracts have bounded Unicorn transition coverage,
including 70 native screen tables. The Playlist page browses larger libraries,
including 200-song menu and jukebox banks, while installing at most 100 selected
records. Library verification reads the installed XBE and actual rebuilt AUSB
descriptors before publication. Playlist documents persist in named and recovery
projects through a validated Build settings map.

Protected Build/Studio integration is supplied in `WIRING.md` and the reviewable
`docs/mod_editor/music_all_modes_wiring.patch`. Those sources were not edited.
The patch passes application and compilation checks and four functional tests
against proposed code in memory. Applying that handoff and regenerating the
protected cave manifest remain integration work for Claude, as required by the
brief. No push, release packaging or gameplay claim is included.

## PROVED: bounded context matrix

Every row below is covered by `test_each_named_policy_transition` subtests in
`tests/mod_editor/test_nfl2k5_music_playlist_contexts.py`. The machine-readable
matrix is `reports/music_playlist_contexts.v1.json`; it includes table addresses,
40-byte table fingerprints, policy, bounded proof flag and a false witness flag
for every row. Additional tests cover source-table identities, real replay
navigation, completion timing and all exclusion states.

For table routes, the native `0x6E390` push, `0x6E4E0` event interpreter and
`0x6E400` pop execute with unchanged event tables. Rendering, navigation setup
and unrelated screen callback bodies are explicit stubs. The draft entry
callback is retained. Each table test enters and exits, checks song/cursor
continuity, then delivers completion and repeated activation, proving one next
enqueue. This proves the music transition contract, not the complete screen
application or every action inside it.

| Context | Chosen policy | Bounded native evidence |
| --- | --- | --- |
| Main menu | Shared shuffle | Main Menu table `0x515660`, push/event/pop |
| Quick Game setup | Shared shuffle | Team Select `0x52728C`; Main Menu item `0x5154C0` points to it |
| Options | Shared shuffle | Tables `0x503288`, `0x503458`, `0x503628` |
| Franchise desk | Shared shuffle | Coach's Desk table `0x522190`, `coach_desk` resource |
| Franchise calendar | Shared shuffle | Table `0x522828`; Calendar In callback `0x142880` installs it at `0xAA2408` |
| Franchise rosters | Shared shuffle | Team Rosters tables `0x555098`, `0x5557C0` |
| Franchise free agency | Shared shuffle | Free-Agent Wire tables `0x53EC38`, `0x583470` |
| Franchise draft menus | Shared shuffle | NFL Draft tables `0x560168`, `0x5603E4`; actual `0x325E10` entry retained |
| Season entry | Shared shuffle | Table `0x528660` |
| Tournament entry | Shared shuffle | Tables `0x5289C8`, `0x52A880` |
| Practice entry | Shared shuffle | Table `0x529344` |
| Crib entry | Shared shuffle | Native block `0x27836B..0x278375` calls mode 3; full 3D initializer outside proof |
| Crib exit | Shared shuffle | `0x270600` clears `0xAC7444` and selects mode 1; teardown stubs |
| Jukebox preview | Temporary explicit preview, then shared restart | `0x27FF90`; disc and HDD preview completion tests, stale callback isolation |
| Game background | Shared shuffle | Native block `0x64899..0x648A3` selects mode 4; profile stop hook `0xF64CD` |
| Pause menu | Continue shared music | Tables `0x4E8D70`, `0x4E9078` while mode 4 remains active |
| Replay | Continue shared music | Actual pause Replay item `0x4E8DD4`, callback `0x6E870`, native push to `0x4FAED8` |
| Loading | Keep timed loading music; suspend shared song | `0x64590` selects mode 2; real `0xF5410` starts controller `0xA928A4`; scheduler `0xF5430` pinned |
| Halftime | Keep timed speech/bed; suspend shared song | Actual `0xD90F0`, nonempty five-entry descriptor, real range/packet helpers, separate speech/bed queues; exit `0xD9350` |
| Wrap-up | Keep timed show music; suspend shared song | `0x28F7F0` saves mode and starts native timed controller; `0x28F860` restores shared mode |
| Draft presentation | Replace scheduled ambience with shared shuffle | `0x325E10` reaches patched call `0x325E22`; clear `0xBD9444`, execute real scheduler `0x165CA0`, prove no separate ambience enqueue |
| Stadium manager and PA | Preserve separate PA; pause/resume shared song for clip preview | Actual `0x3592A0 -> 0xF65F0 / 0x254EB0` and `0x359280 -> 0xF65E0`; clip decoder/profile I/O stubbed |
| Create a player | Shared shuffle | 44 tables: Create Player `0x56E9C4`, 34 attribute tables `0x56A560..0x56E760` at stride `0x200`, nine editor/menu tables listed in JSON |
| Create a team | Shared shuffle | Six tables `0x57173C`, `0x571AB0`, `0x571BD8`, `0x571E58`, `0x571F90`, `0x572018` |

`all_modes_proved=True` in the matrix and installed receipts means these **24
bounded routing contracts only**. `context_proof_scope` qualifies it and
`runtime_witnessed=False` remains explicit. Neither a checkbox nor the presence
of a hook is treated as a gameplay witness.

Two tier-4a assumptions were corrected. The modal pause/resume wrapper belongs
to stadium clip previews, not Replay. Real pause/replay screens continue the
shared song. Also, `0x325E22 -> 0x165BE0` is the actual draft entry request for
`draftambience`; the earlier `0x165C20` evidence concerned `coachambience`.
This version deliberately replaces that request with the shared shuffle and
clears the scheduled descriptor. It does not assume `draftambience` aliases
the archive bank `drafta`. The alias remains unproved and is unnecessary for
this policy. Archive/name searches did not establish it.

Halftime coverage uses a nonempty descriptor and executes the native packet
and range builders: observed indices are `2,4,1,1,3`, with controller queues
`0xB73B64` for speech and `0xB73B1C` for the bed. Allocation, stream binding,
mixing and audio I/O are stubs. Loading starts the native controller but does
not prove its complete long-running schedule. PA wrapper and byte preservation
are proved; audible PA/music coexistence is not.

## Native ownership and composition

The two new live hooks are screen dispatch `0x6E4E0` (five displaced bytes) and
draft initialization call `0x325E22` (five-byte CALL). Screen activation saves
registers/flags, services pending music only for events 1 and 3 after normal
initialization, preserves exclusion states, then executes the displaced
prologue and complete native dispatcher. Draft's adapter preserves registers
and the native two-argument stack cleanup.

The owner remains `nfl2k5_music_playlist`, with requests **2,048 RX / 512 RW /
1,024 RO bytes**, 16-byte alignment. Generated code is **1,689 bytes**. No new
owner, page request, retail cave or runtime writable `.text` storage is used.
The existing budget fixture, union helper and all manifest owner lists already
contain the correct owner and requests. The allocator plan passes with 37
requests and a 12,300,288-byte XBE. The assembler's reproduction check passes.

Both full XBE gates initially exposed a real composition conflict: Practice
Squad pinned the screen dispatcher prologue now owned by the playlist. Its
unprotected guard now accepts that prologue only when the complete playlist
installation is validated, then hashes the remaining native bytes. Both owner
orders pass the full memory-write and cave-reference gates after this fix.
Foreign/mixed bytes still refuse before mutation and ordinary section digests
are repinned by existing helpers.

Tier-4a installed code is intentionally foreign to this version. Rebuild from
the supported source when moving to tier 4b or changing an installed selection;
there is no implicit conversion of an old installation.

## PROVED: larger libraries and publication

Schema 2 separates the browse catalogue from the installed selection. Up to
400 songs per main bank plus ten audited beds can be browsed; at most 100
selected visible records are serialized into runtime storage. Schema 1 imports
remain supported. The outtake and bed switches preserve hidden checkbox
choices, but hidden rows consume no installed-record capacity. An extra click
or filter change that would exceed 100 is rolled back without emitting an
invalid Build document. Select All refuses when the visible library exceeds
100. Zero records stops and one record repeats.

Library previews supply actual plan titles; reading a rebuilt image supplies
actual jukebox metadata and AUSB counts. Authored music at old outtake indices
is not mislabeled as spoken outtakes. Changing catalogues preserves choices by
`(bank,index)` where those records still exist; missing choices drop and the
visible selection count updates. Importing saved JSON restores its catalogue
and selection. This is a browse/selection feature; fixed-slot audio editing
still has its existing retail geometry limits.

`read_descriptor_counts` and `read_playlist_catalog` reopen bounded archive
readers and check source identity before/after. `playlist_preflight` combines
actual counts with validated planned boundaries and retains a false final
revalidation flag. `_validate_playlist` reads the installed XBE selection,
checks its complete installation, validates actual indices and stereo/mono
twin geometry, and optionally matches the expected Build document exactly.
`verify` calls it before the library writer publishes. `revalidate_playlist`
provides the final Build publication gate in the protected handoff, including
after Hi-res remapping.

Synthetic disc tests use the real executable and generated tiny tones, with
streamed archive rewrites and immediate cleanup. A 200-entry menu bank accepts
100 installed indices `100..199`; a 200-entry jukebox rebuild validates both
`cribmusic` and `crib22` and reads the real authored title at index 199. Bounded
native enqueue coverage consumes every high index once and avoids a repeat at
the next cycle boundary. Invalid shrink, corrupted installed RO, bad descriptor
counts and a mismatched expected document refuse. Source and existing target
remain unchanged on publication failure, and readers close before replace.

The core module has a bounded `python3 -m ...nfl2k5_music_playlist` status/apply
entry point so the capability command resolves to its package module. It reads
at most 16 MiB of executable data and never overwrites its target. This is an
executable-only development command; it explicitly reports that descriptor
validation is still required before image publication.

## PROVED: project persistence and protected handoff

Project archives now accept an optional validated `build_settings` music map.
The complete playlist JSON, filters, checked rows and enable flag survive named
save/open and recovery save/open. Maps and documents are detached on reads;
invalid imports clean their private staging directories and invalid saves
preserve the old project. Session manifest failures roll back state. Projects
containing only Build settings are valid; older projects load empty settings.
Asset Revert All and its Undo retain preferences.

The protected patch adds Build state capture/restore, fixes the old setter's
dictionary-to-`Selection` storage error, connects both enable switches, caches
choices across lazy page creation, and restores without emitting dirty-state
updates. It carries accepted library previews and actual rebuilt catalogues to
Music. Four handoff tests execute the proposed code in memory with real
offscreen widgets and a small Studio host, plus the final publication wrapper.
The wrapper test proves validation sees the final private bytes before replace
and a validation exception leaves both source and destination intact.

## Tests and limits

These commands passed. Qt commands run offscreen; native tests are bounded
Unicorn instruction tests, not an Xbox emulator. Standalone music tests include
their own repository path setup and explicit missing-evidence/dependency skips.
No relevant evidence tests were skipped in this run.

| Command | Result |
| --- | --- |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | PASS, 37 requests |
| `python3 tools/nfl2k5_music_playlist_assemble.py --check` | PASS, template reproduced |
| `python3 tests/mod_editor/test_nfl2k5_music_playlist.py` | 15 PASS |
| `python3 tests/mod_editor/test_nfl2k5_music_playlist_contexts.py` | 7 PASS, all 24 rows and 70 tables |
| `python3 tests/mod_editor/test_nfl2k5_music_playlist_library.py` | 7 PASS |
| `python3 tests/mod_editor/test_nfl2k5_music_playlist_manifest.py` | 2 PASS |
| `python3 tests/mod_editor/test_nfl2k5_music_banks.py` | 15 PASS |
| `python3 tests/mod_editor/test_nfl2k5_music_policy.py` | 8 PASS |
| `python3 tests/mod_editor/test_nfl2k5_music_metadata.py` | 6 PASS |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_music_panel_qt.py` | 9 PASS |
| `python3 tests/mod_editor/test_music_playlist_project.py` | 4 PASS |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_music_all_modes_wiring.py` | 4 PASS |
| `python3 tests/mod_editor/test_nfl2k5_practice_squad_screen.py` | 10 PASS |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 63 PASS, both composition orders |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 75 PASS, both composition orders |
| `PYTHONPATH=. python3 tests/mod_editor/test_studio_session.py` | 18 PASS |
| `PYTHONPATH=. python3 tests/mod_editor/test_project_archive.py` | 6 PASS |
| `PYTHONPATH=. python3 tests/mod_editor/test_studio_facade.py` | 11 PASS |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_project_document_workflow.py ProjectTargetSafetyTests ProjectArchiveBoundTests` | 7 PASS |
| `git apply --check docs/mod_editor/music_all_modes_wiring.patch` | PASS |
| `python3 -m mod_editor.capabilities.validate_registry --skip-file-checks` | PASS, full registry schema/semantics/canonical encoding |
| Playlist evidence paths and exact module commands via `validate_registry._local_path` / `_command_module`, plus registry/docs object equality | PASS, scoped file checks |
| `python3 -m mod_editor.core.nfl2k5_music_playlist --help`, changed Python compilation, `git diff --check` | PASS |

The full existing `test_project_document_workflow.py` ran 13 tests: seven
passed and six GUI-construction cases errored because this worktree lacks
`reports/assets`, required by the unchanged uniform catalogue loader. No fake
assets or new skips were added. The initial plain invocations of older session
tests lacked their repository import path; the table records the successful
`PYTHONPATH=.` invocations. Initial composition failures were fixed and both
complete gates rerun successfully, not skipped.

Full registry file validation (`python3 -m mod_editor.capabilities.validate_registry`)
stops on the pre-existing missing `docs/research/apf_audio.md` at capability 0.
All files and commands for the changed playlist entry were checked explicitly;
unrelated entries were not rewritten to hide missing evidence.

The old archive-mechanics fixture has a 16-byte fake XBE header; that suite
explicitly mocks playlist inspection. The separate new library suite uses the
real executable and unmocked installation/descriptor validation for all
publication claims. Tests never load a full disc or pack into RAM.

No full retail-disc build was started: the first disk check showed 95 GiB free,
below the requested 100 GB floor. A later check showed 101 GiB; creating a
6.3 GB disposable disc there would again cross the floor. Read-only retail
research and small synthetic fixtures were sufficient for the bounded task.
All disposable images/packs lived in `TemporaryDirectory` and were removed.
Scratch held under 1 MiB of code, JSON and logs before the small commit bundle.

## HYPOTHESIS and Noah's witness list

Actual stream completion timing, decoder behavior, audible mixing, volume and
stereo/surround behavior remain unwitnessed. No claim covers arbitrary unnamed
screens, every action inside a screen, full Crib 3D initialization, the complete
long-running loading schedule or the original draft resource alias.

After Claude applies the handoff and regenerates the manifest, Noah should:

1. Build from the supported source with default 66, outtakes off (54), beds on,
   zero, one, two and 100 selected songs from a 200-song library. Confirm both
   menu and jukebox high-index selections, each full cycle and its boundary.
2. Enter and leave every matrix row, including each franchise submenu, player
   attribute/editor screen and team editor. Verify song/cursor continuity and
   one advance when a song ends during a transition. Exercise controller and
   profile changes, Crib entry/exit and repeated game/menu transitions.
3. Confirm pause and actual Replay continue music. Confirm draft shares the
   playlist without separate ambience. Test draft picks and speech, stadium
   clip previews and live PA, including stereo/surround and volume settings.
4. Confirm loading, halftime and wrap-up keep their timed audio with no shared
   overlap, then restart the selected background song. Exercise explicit disc
   and HDD jukebox previews, completion, cancellation and return.
5. Save/open a project before and after opening Build, restart Studio, recover
   a project and open an older project. Confirm catalogue, filters, selected
   high indices and both enable switches agree; all presets remain off.
6. Build with a library recipe and other selected resource edits, inspect the
   final `music_shuffle_validation` receipt, and test an invalid shrink against
   an existing destination. Verify the previous destination survives refusal.

Until these are played and recorded, runtime evidence remains **not tested**.
