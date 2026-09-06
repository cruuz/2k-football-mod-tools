# Franchise Practice exit correction

Public path notation: `<home>` and `<media>` identify the original local home and mounted input directories. Recorded hashes, measurements and outcomes are unchanged.

2026-09-06. Base: `f371972f4a17cecf654c019d5c6ff3a3c32c7caa`.
**EXPERIMENTAL / UNWITNESSED.** Noah witnessed the previous build returning to
Main Menu. This correction has bounded CPU and offline patch evidence, not a
played witness. No emulator, GUI, audio or network was used.

## Result and scope

Franchise Practice START now removes its settings screen once and pushes the
retail game screen. Quit can find that screen, unwind the pause menus, tear the
game down and resume the existing Coach's Desk. The correction also supplies the
normal scene loader that the previous direct restart skipped.

The owner remains `mod_editor/core/nfl2k5_franchise_practice.py`. Its three stubs
occupy 107 bytes, previously 100, within the existing 160-byte code capacity of
the reserved 352-byte cave at `0x1D82D0..0x1D8430`. No new allocation, runtime
flag, executable-section state, save field or user switch is added. The four
existing edit sites, cloned settings descriptor, callbacks and Coach's Desk
row layout retain their addresses. No live retail instruction is overwritten
by this owner. Section digests are recomputed through the existing writer.

`tests/mod_editor/test_nfl2k5_franchise_practice.py` now expects the correct
START tail. The new standalone exit suite executes native screen management
and game-exit instructions. The reserves suite received the missing repository
`sys.path` setup so plain `python3 file.py` works as required by CI.

## Retail evidence and exact route

All addresses below are Xbox virtual addresses in the USA retail XBE:

- File size: 11,948,032 bytes.
- SHA-256: `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
- Feature-only patched SHA-256: `6a9008b9e3aaf6c83a60418a72c8fd8dc1cf3cc90059a385d39addea17b871c9`.
- Input: `<media>/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe`.
- Ghidra: read-only `research/functions/nfl2k5/pseudo_c` under the main repository.
  Relevant records include `FUN_000617E0`, `FUN_00062BE0`, `FUN_00064530`,
  `FUN_00064CD0`, `FUN_0006E400`, `FUN_0006E450`, `FUN_0006EBE0`,
  `FUN_0006ED30`, `FUN_0006EE50`, `FUN_002C0E70` and `FUN_00148B50`.
  Some indirect callback bodies and jump-table arms are absent or incomplete
  in that export. Their exact bytes were decoded from the pinned XBE with
  Capstone 5.0.7; addresses and literals are also checked by standalone tests.

### Settings START was a restart, not initial game entry

The Scrimmage Settings descriptor is `0x501834`, with START at descriptor
`+0x30 -> 0x148B50`. That routine writes 1 to `[[manager+0x10C]+0xA84]`, pops
**twice**, and jumps to `0x64B10`. The state field suppresses the generic Back
handler's additional pop; it does not create a game-screen entry.

`0x64B10` calls `0x125C50`, `0x649C0`, `0x617E0`, `0x64710`, then tail-jumps
to `0x125700`. It restarts an already loaded game. It never pushes a screen and
does not call the initial scene loader `0x64590`. Retail Restart (`0x6EC90`)
and Rematch (`0x6EDA0`) explicitly unwind to the game screen before using it.
That is the missing precondition in the previous franchise launcher, which
copied the restart with one pop and started with Coach's Desk underneath.

Initial game entry uses descriptor `0x4E7EC0`. Retail menu launch dispatch
`0x2C0E70` selects a context-specific route: the arm at `0x2C0E7C` unwinds to
Main Menu `0x515660` and pushes the game; the arm at `0x2C0E94` replaces the
current screen with the game using `0x6E2E0`. Both install the game descriptor.
There is no universal fixed Main Menu target in Quit itself.

### Game screen and teardown

The descriptor's event list is `0x4E7E88`; its six records start at `0x4E7CD8`:

| Event | Callback | Meaning in this route |
| --- | --- | --- |
| 1 | `0x64C70` | Load scene through `0x64590`, initialize through `0x64710`, then `0x125700` |
| 3 | `0x64620` | Resume timing |
| 2 | `0x64CA0` | Destroy game and restore menu resources |
| 5 | `0x64650` | Suspend timing |
| 6 | `0x650A0` | Update, starting with `0x64CD0` |
| 9 | `0x64F80` | Render game |

`0x6E390` pushes: suspend the previous screen, increment `[manager+0x100]`,
store the descriptor in the eight-byte slot, dispatch event 1 and then event 3
if the enter handler succeeds. `0x6E400` pops: dispatch events 5 and 2 to the
current screen, decrement depth and dispatch event 3 to the exposed parent.
`0x6E450` repeatedly pops until it finds the requested descriptor or reaches
root. It does not recreate a missing target.

The native pause menu is `0x4E9078`. Its Quit submenu row at `0x4E9010` points
to `0x4E8D70`; the action row at `0x4E8CA0` has callback `+0x28 -> 0x6EBE0`.
For the offline path:

1. `0x6EBE0` checks the retail confirmation branch, using `0x14E440` when
   needed. Result 3 cancels and keeps the paused game.
2. Accepted Quit clears input/pending work, calls `0x64B60` with ECX 0 to set
   `[0xA83A18] = 0`, and calls `0x6E450` with EDX `0x4E7EC0`.
3. Pause/submenus are removed, leaving the game screen on top. Quit itself has
   not yet returned to the menu parent.
4. The next game event 6 runs `0x650A0 -> 0x64CD0`. Any state other than 3
   takes the direct `0x6E400` path.
5. Game event 2 invokes `0x64CA0`. If `[0xA83A10]` is nonzero it calls
   `0x125C50` and the engine destructor `0x649C0`; it then calls `0x645D0`
   to unload scene resources and restore the menu resource context.
6. The native pop exposes the original parent. For this feature that is the
   already loaded Coach's Desk, descriptor `0x522190`.

With the previous launcher, step 2 could not find `0x4E7EC0` and popped
through Coach's Desk to root/Main Menu. The new regression reproduces that
exact stack unwind and the missing game-destructor event. This is a proved
instruction-level explanation of the observed destination, not a new gameplay
witness of how the previous build loaded its graphics.

### Franchise game end as the return model

The retail End Game action `0x6EFE0` calls result processing `0x6EE50`, sets
game state 2, unwinds to the game descriptor, and pushes postgame menu
`0x4E935C`. Postgame Quit `0x6ED30` calls `0x12BB60`, `0x12BDE0` and
`0xCF840`, then pops that menu. The next game update removes the ended game
using the same event-2 teardown and resumes the retained franchise parent.
The test includes a Franchise postgame fixture with Desk as its retained parent
as a positive control.

The distinction from Practice is in season processing. Inside `0x645D0`,
only modes 5, 6 and 7 call `0xC5D60`. That helper ignores game states 0/1;
otherwise it addresses the scheduled game using `[0xE576B4]`, `[0xE576BC]`
and table `0xE57C40`, calls `0x1C1C80`, `0x1356C0` and `0x134140`, then sets
`0xE576A8` through `0xC4BC0`. Practice modes 0, 1 and 2 skip this entire
season-completion branch. The new tests execute this guard, including positive
controls for modes 5/6/7. The season-changing helper itself is a named service
boundary in the positive control, not a simulated completed season game.

The correction adopts the parent's screen lifetime. It does not call a fresh
Coach's Desk initializer or replay postgame season processing. In particular,
`0x13F1B0`, which ultimately pushes Coach's Desk, also iterates player and
franchise state; it is not a safe shortcut for a practice return.

### Completion and source roster

No distinct finite Free Practice completion trigger was established in this
study. The native state test is explicit: if a session finishes with state
0, 1 or 2 and reaches its game update, the same teardown/pop returns to the
retained parent. Tests inject those terminal states; they do not claim that
ordinary practice reps cause a natural session end. Any in-game Finish/End
route Noah encounters still requires the witness below.

The new initial loader retains reserve staging:
`0x64590` (call at `0x645AF`) -> `0x62BE0` (offline call at `0x62CFD`)
-> `0x617E0` (call at `0x617F3`) -> `0x61730`.
`practice_reserves` owns that last routine and extends only the disposable
team/player copies for league type 1 and practice modes 0..2. Its source-roster
and depth-chart preservation tests still pass. The new exit harness also
snapshots `0xE576A0..0xE57C40`, source-roster pointer `0xB72918`, and separate
synthetic roster/depth/player storage through launch, Quit and teardown.

## Patch mechanics and evidence boundaries

The new START sequence at `0x1D83D6` is:

```text
push esi
mov esi, ecx
mov eax, [esi+0x10c]
mov dword [eax+0xa84], 1
call 0x6e400
mov ecx, esi
mov edx, 0x4e7ec0
pop esi
jmp 0x6e390
```

Restoring ECX matters: the pop and its callbacks may clobber volatile registers.
The game screen enters with the original manager and the saved ESI is restored.
The depth evolution is:

```text
0 Main Menu, 1 Coach's Desk, 2 Settings
START: one pop, one push -> 0 Main Menu, 1 Coach's Desk, 2 Game
Pause:                   -> 0 Main Menu, 1 Coach's Desk, 2 Game, 3 Pause
Accepted Quit:           -> 0 Main Menu, 1 Coach's Desk, 2 Game
Ended update/teardown:   -> 0 Main Menu, 1 Coach's Desk
```

**PROVED within the bounded harness:** Unicorn 2.1.4 executes the installed
START, native push/pop/pop-to, game event dispatcher, game enter, accepted and
cancelled Quit, ended-state update, game teardown and its practice/season guard.
It also executes the practice early return in `0x125700`. Main `.text` is mapped
read/execute. Each call is capped at 20,000 instructions; ESP and ESI preservation
are asserted. The old missing-game stack unwinds through the Desk; the corrected
one retains it and invokes teardown once. Failed initial loading also returns
to the Desk without starting the engine.

The existing retail flag `0xE5FFE4` is tested set and clear, and remains unchanged.
It is a loader-context flag, not a new franchise-practice exit flag. With a Desk
parent, modes 0/1/2 return to the Desk for either flag value. With the flag clear
and retail Main Menu at depth 0, the untouched retail game/exit instructions
return to that Main Menu at depth 0. Destination follows the retained parent.
The feature does not override unrelated Practice exits globally.

**Explicit service boundaries:** scene loading, engine initialization and
resource destruction; non-game menu rendering/events; modal UI; offline/network
queries and resource-manager calls. Source snapshots and skipped season commits
are proved for the executed instructions and these stated service contracts.
The tests do not prove that every instruction inside those services preserves a
real loaded franchise. Full scene loading/rendering, long sessions, controller
interaction, season simulation and save persistence remain **HYPOTHESIS /
UNWITNESSED** until Noah plays them.

New pins cover the complete retail game descriptor, its event list and records,
the screen-push routine and the game-enter routine. Exact replay is unchanged;
foreign or mixed bytes refuse before mutation. The previous already-patched
START is deliberately foreign, so integration must rebuild from retail rather
than migrate an old partly patched XBE.

## Composition and validation

`practice_reserves` and `practice_squad_screen` require Franchise Practice as a
prerequisite. Tests cover both independent installation orders where legal,
all three modules replaying in both orders, a grown-section screen descriptor
replacing the Desk row pointer, preserved Practice/Practice Squad rows, and the
exit sequence on both the feature-only and composed image. The existing complete
owner union already includes these features. Both gates exercise forward/reverse
allocator-owner orders and the normal/scaled layouts, so no new owner registration
was needed.

All commands below were run standalone with plain Python, no pytest or emulator.
No tests were skipped with the available retail XBE, Capstone and Unicorn.

| Command after `python3` | Result |
| --- | --- |
| `tests/mod_editor/test_nfl2k5_franchise_practice.py` | 22 passed, 12.154 s |
| `tests/mod_editor/test_nfl2k5_franchise_practice_exit.py` | 13 passed, 12.480 s |
| `tests/mod_editor/test_nfl2k5_practice_reserves.py` | 9 passed, 14.548 s |
| `tests/mod_editor/test_nfl2k5_practice_squad_screen.py` | 10 passed, 47.772 s |
| `tests/mod_editor/test_nfl2k5_practice_squad_screen_unicorn.py` | 14 passed, 6.591 s |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 59 passed, 158.913 s |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 71 passed, 239.595 s |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | 27 passed, 1 error, 69.196 s: protected manifest has the previous owner source fingerprint |

The manifest failure is specifically
`test_retail_current_stack_owns_every_supplied_cave_and_runtime_flag`:
`stale reservation source: mod_editor/core/nfl2k5_franchise_practice.py; regenerate manifest`.
A direct fingerprint audit found no other stale source. The manifest's full
existing owner capacity covers every new cave byte; the new test and both gates
pass that coverage check. No hash was changed by hand and no freshness check was
suppressed. Claude's protected regeneration and UI-copy corrections are spelled
out in `WIRING.md`. The final manifest freshness check remains an integration gap.

During development, a new test initially expected the wrong code size (111
instead of 107), and the reserves script initially failed its standalone import.
Both were corrected; the final results above supersede those runs.

Only bounded XBE and synthetic fixtures were read. No whole disc or archive pack
was loaded into memory. Recorded maximum RSS for the timed suites was below
906 MiB (the oracle); the exit suite was below 600 MiB. No disposable disc or pack
was built or retained. Root free space was about 102 GiB at checks and fluctuated
externally; this work's scratch receipts/logs remained below 1 MB before the Git
fallback. A new 6.3 GB disposable disc would not leave a conservative 100 GiB
margin. The real-disc manifest rebuild was therefore left to the designated
integrator with sufficient space. Scratch artifacts are local, not committed.

## Noah's required played witness

1. Build from the pinned retail input with `franchise_practice` and the current
   stack. Start with a disposable franchise save. Record week, next scheduled
   game/opponent, wins/losses, roster/reserve counts and a distinctive depth-chart
   ordering. Load the Coach's Desk.
2. Open Practice below Schedule. Confirm your coached team is on both sides and
   Full Scrimmage loads on the practice field. Run several plays.
3. Pause, select Quit/Exit Practice, cancel once, and Resume. Confirm the same
   session continues. Pause again, accept Quit, and verify the destination is
   **Coach's Desk**, with working controls and menus.
4. Check the recorded week/game, record, roster, reserves and depth chart. Practice
   must not mark a scheduled game played, consume a week or alter those lists.
5. Enter and quit Practice again. Open the Practice Squad table, promote/release
   only if intentionally testing those controls, and check that its rows and
   navigation still work. Repeat with both reserves and the new screen enabled;
   confirm reserves can appear in practice while the saved active depth chart
   stays intact. Use a separate save for deliberate roster transactions.
6. Repeat Quit in Special Move and Offense Only. If any mode exposes a natural
   Finish/End Practice route, exercise it and verify the same Desk return and
   unchanged week. Do not count a rep resetting as a completed session witness.
7. **Then advance exactly one week** using the normal franchise action. Verify
   the expected next opponent/week, normal season processing and usable Desk.
   Save, exit and reload; confirm the resulting franchise still opens normally.
8. As controls, enter Practice through retail Game Modes and Quit to its normal
   parent; play/end a scheduled Franchise game and verify its normal postgame
   return and exactly one legitimate game/week update. Record build hash, save,
   mode, destination and any freeze, resource/audio issue or unexpected update.

## Delivery

All protected files remain untouched. `WIRING.md` is the concrete integration
handoff. Staging the six explicit deliverable paths was refused with
`index.lock: Read-only file system` in the external Git metadata. The authorized
fallback is `.scratch/r62-franchise-practice-exit.bundle`, created with separate
scratch Git metadata and the original base as its parent. The edited files are
also left in this worktree. Neither `ASTRA_BRIEF.md` nor `.scratch/` is included
in the commit. Nothing is pushed.
