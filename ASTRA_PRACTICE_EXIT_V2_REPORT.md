# Franchise Practice exit v2

2026-09-07. Base `e997a8e`, branch `astra/r63-practice-exit-v2`.
**EXPERIMENTAL / UNWITNESSED.** Noah witnessed the previous correction returning
to Main Menu. This revision has pinned executable and bounded Unicorn evidence;
Noah has not played it. No console emulator, GUI, audio or network was used.

## Result

The destination is lost at **Team Select launch**, before the practice rep.
The previous analysis mistook a following event record for a descriptor field:
`0x501834 + 0x30` is not a START handler. Consequently neither previous cave
START stub ran when the player pressed START. The old test invoked that unused
stub directly and omitted the native route that destroys Coach's Desk.

This revision preserves Team Select, its controller/team setup, the scene
loader and the retail pause Quit callback. A guarded five-byte hook in the
existing launch arm chooses Coach's Desk instead of Main Menu only for the
exact Franchise Practice stack. All code remains in the existing owner's
352-byte cave: **135 of 160 code bytes**, no new allocation or mutable state.

## PROVED: source identity and the actual route

Input read only:
`/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe`.

- Size: 11,948,032 bytes.
- Retail SHA-256: `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
- Exact prior feature-only SHA-256: `6a9008b9e3aaf6c83a60418a72c8fd8dc1cf3cc90059a385d39addea17b871c9`.
- This feature-only SHA-256: `d81023aad98eb2969be2802274594badd31859e958f9b754e928f33cdbcd2643`.

The new test reconstructs the entire prior feature-only XBE using its exact
352-byte cave and asserts the prior full-image hash. It reproduces the bad
route on that fixture and the corrected destination on the new fixture.
This is stronger than manufacturing a missing game-screen stack; it is still
CPU evidence with the service boundaries below, not a new played witness.

Read-only corpus: `/home/noah/2k-football-mod-tools/research/functions/nfl2k5/pseudo_c`.
Relevant exported bodies include `FUN_0006E450`, `FUN_0006EC90`,
`FUN_00064CD0`, `FUN_000F3970`, `FUN_00150020`, `FUN_00148B50`,
`FUN_002C1700`, `FUN_002C1950` and `FUN_002C0E70`.
The last export explicitly says it could not recover the jump table.
`0x6EBE0`, `0x6EDA0`, `0x645D0` and `0x2C21C0` have no standalone
exported body in this corpus. Their instructions and the descriptor records
were decoded from the pinned executable with Capstone and executed in Unicorn.
No missing export was treated as proof that a callback is unused.

### START and the missing parent

1. A screen descriptor is **44 bytes**, through the flags at `+0x28`.
   Settings `0x501834` has flags `0x55`, including START bit `0x40`.
   Native input `0xF3970` tests controller START `0x10`; at `0xF3ACE`
   it supplies event `0xB` to `0x6E4E0`.
2. The settings hook list `0x5016AC` maps event `0xB` to record
   `0x5015F8`, kind 1, callback `0x148B40`. The cloned settings list
   retained this mapping in both prior versions and still does.
3. `0x148B40` pushes Team Select descriptor `0x5275F8`. Its event-1
   record `0x5274F8` calls `0x2C21C0`, which supplies EAX **3** to
   `0x2C1950`; instruction `0x2C1959` stores 3 at `0xACF614`.
4. Team Select's event-`0xB` record `0x527468` calls `0x2C1700`.
   Offline readiness/team checks lead to `0x2C0E70`. The jump table
   uses `0xACF614`, not the practice mode word, to choose its arm.
5. Context **3** selects `0x2C0E7C`: load EDX `0x515660` (Main Menu),
   restore ECX from ESI, call pop-to `0x6E450`, then push the game
   descriptor `0x4E7EC0` through `0x6E390`.
   The old pop-to destroys Team Select, settings and **Coach's Desk**
   when Main Menu is below the Desk. No Desk remains to resume at Quit.

The apparent START field was actually the beginning of the next event record:
`0x501860` is kind 1 and `0x501864` is callback `0x148B50`.
The hook list `0x5018F0` references that record for event `0xB` and the
next record `0x5018A8` for event `0xA`. That list belongs to **in-game**
Scrimmage Settings descriptor `0x501A74`. Its restart pops twice and jumps
to `0x64B10`. Copying its callback into an unreferenced descriptor suffix
could not change pregame START. The native in-game restart stays untouched.

The other launch arms are verified: contexts 4/5/6 select `0x2C0E94`,
which replaces the current screen with the game; context 8 shares the fixed
Main Menu arm; contexts 0/1/2/7/9 select `0x2C0EA0`. These alternatives
are not the context-3 route initialized by this Team Select screen.

### Pause-menu Quit through Coach's Desk resume

From an active offline rep, game event 6 executes `0x650A0`. Its native
controller START handling pushes pause descriptor `0x4E9078`.
The next two controller-A activations execute the native list handler
`0x150020`:

- Pause row **12**, `0x4E9010`, is type 0. It reads `+8 -> 0x4E8D70`
  and pushes the Quit submenu through the arm at `0x1501D5`.
- Submenu row **2**, `0x4E8CA0`, is type 9. The arm at `0x15021F`
  calls `+0x28 -> 0x6EBE0`. Its visibility callback is `0x6EBA0`;
  practice modes expose it, while modes 5/6/7 hide it.
- `0x6EBE0` handles the retail confirmation branch. Result 3 cancels.
  Accepted Quit clears pending input, sets `[0xA83A18]=0` through
  `0x64B60`, and pops to **the game descriptor**, not Main Menu.
- On the next game update, `0x650A0 -> 0x64CD0` sees state other than 3
  and calls `0x6E400`. Event 2 invokes `0x64CA0`: `0x125C50`, engine
  destruction `0x649C0`, then scene/menu restoration `0x645D0`.
- The native pop dispatches event **3** to the retained Coach's Desk.
  Its `0xF3E90` handler takes `0xF3ECB`, calls the normal menu setup,
  and `0x14FF80` rebuilds rows from the Desk descriptor's current table.
  The test executes this row rebuild, including the delegated Practice
  Squad table, rather than stopping when the Desk pointer becomes topmost.

`0x6EC90` is attached to the pause Quit submenu's **Rematch** row
`0x4E8CD4`, not its Quit row. It pops to the game and restarts through
`0x64B10`. `0x6EDA0` is the other Rematch callback (pointer at
`0x4E9218`); it also pops to the game and restarts. Neither executes
in the tested player Quit chain. The old report's blanket statement that
there is no fixed Main Menu unwind missed the fixed target at launch.

## Implementation and ownership

`mod_editor/core/nfl2k5_franchise_practice.py` replaces only:

```text
0x2C0E7C: mov edx, 0x515660   ->   call 0x1D83D6
```

The 65-byte target stub at `0x1D83D6` defaults to Main Menu. It chooses
Coach's Desk only when all conditions hold:

- unsigned game mode `0xE5FF80` is 0, 1 or 2;
- manager depth is at least 2 and below 32;
- the top descriptor is native Team Select `0x5275F8`;
- the immediately preceding descriptor is **this owner's clone** `0x1D8340`;
- the preceding descriptor is Coach's Desk `0x522190`.

It only reads context and returns EDX. ECX, ESI and the stack are preserved;
EAX and flags are dead at this point in the native arm. No state flag can
survive cancellation or accidentally affect the next scheduled game.
Foreign/missing parents and ordinary retail Practice use the original target.

Typical depths with Main Menu below Coach's Desk:

```text
Before first START:  0 Main Menu, 1 Coach's Desk, 2 cloned settings
Team Select:        0 Main Menu, 1 Coach's Desk, 2 cloned settings, 3 Team Select
Old game launch:    0 Main Menu, 1 Game
Corrected launch:   0 Main Menu, 1 Coach's Desk, 2 Game
Pause / Quit menu:  0 Main Menu, 1 Coach's Desk, 2 Game, 3 Pause, 4 Quit
Accepted Quit:      0 Main Menu, 1 Coach's Desk, 2 Game
Ended update:       0 Main Menu, 1 Coach's Desk
```

The tests also cover the Desk itself at root: corrected launch/quit retains
that root. No function recreates a missing Desk or invokes `0x13F1B0`.

The original four sites remain, plus the five-byte launch hook. Cave bounds,
row/enter callback addresses, hook tables and clone address remain fixed.
The clone now contains the actual 44-byte descriptor; unused suffix bytes are
INT3 padding. The old 80-byte retail context pin is retained in full under
`RETAIL_SCRIM_CONTEXT`. All other previous pins and sealed delegation checks
remain. New pins cover the entire launch dispatcher and jump table excluding
only the owned target instruction. `status` rejects old, mixed and foreign
installations before mutation. Rebuild from retail; old patched XBEs are not
silently migrated.

Receipts retain the original edit entries and add `practice_launch_unwind_target`.
They report 135/160 cave code bytes, two settings/Team Select pops and one
game push at launch, exact context/targets, no runtime flag and
`runtime_verified=False`. Feature-only apply changes **424 bytes**, including
section digests; `.text` and `.rdata` are repinned through the existing writer.
Replay returns zero changed bytes. The physical XBE size is unchanged.

The existing owner is already included in both gates and the allocator union;
no new owner, allocator budget or option is introduced. No protected file or
WIRING.md is edited.

## PROVED tests and explicit limits

The new standalone `test_nfl2k5_franchise_practice_exit_v2.py` executes native
input/event dispatch, Team Select context initialization and launch dispatch,
screen push/pop/pop-to, game enter, pause detection, row construction and
activation, accepted/cancelled Quit, ended-game update, teardown's mode guard
and the Desk event-3 row rebuild. Main `.text` is read/execute. Each entry is
capped at 30,000 instructions and checks stack balance and EBX/EBP/ESI/EDI.
The target-only negative fixtures are capped at 100 instructions.

The complete route matrix covers feature-only and reserves/squad-screen
composition, modes 0/1/2, loader flag `0xE5FFE4` clear/set, and Desk depths
0/1: **24 complete routes**. Other fixtures cover the exact bad prior build,
confirmation cancellation then Cancel/Resume and successful Quit, pregame
Back, failed loading, ordinary retail Practice, corrupt/mixed installation,
and missing/mismatched/out-of-range stack contexts and nonpractice modes.

Source-roster pointer, synthetic roster/player/depth storage and
`0xE576A0..0xE57C40` remain byte-identical in corrected practice fixtures.
`0x645D0` skips season commit `0xC5D60` in modes 0..2. The retained lifecycle
suite additionally checks completed states and positive season-mode controls.
The existing reserves suite separately executes the reserve-staging behavior.

**Service boundaries / HYPOTHESIS:** controller hardware reads, modal rendering,
scene/layout allocation and rendering, the active rep simulation body, engine
initialization/destruction, resource loading, Team Select team validation and
preview setup, and audio/network services are bounded substitutes, enumerated
by address in the test. `0xF3CD0` layout setup and `0x142FB0` Desk scene refresh
are service boundaries; event dispatch and native row reconstruction execute.
The test begins with a loaded franchise's initialized settings, not an entire
save load. It does not prove every instruction inside those services or a real
save's persistence. No natural finite Free Practice completion trigger was
established. A played witness remains necessary for controls, scene/audio
restoration, long sessions, repeat entry, subsequent season play and saving.

### Final validation

Commands use plain `python3`; no pytest, disc build or emulator is required.
Each script below ran standalone as `python3 tests/mod_editor/<script>`.

| Script under `tests/mod_editor/` | Result |
| --- | --- |
| `test_nfl2k5_franchise_practice.py` | 22 passed, 12.227 s |
| `test_nfl2k5_franchise_practice_exit.py` | 13 passed, 14.881 s |
| `test_nfl2k5_franchise_practice_exit_v2.py` | 8 passed, 6.213 s |
| `test_nfl2k5_practice_reserves.py` | 9 passed, 15.727 s |
| `test_nfl2k5_practice_squad_screen.py` | 10 passed, 91.290 s |
| `test_nfl2k5_practice_squad_screen_unicorn.py` | 14 passed, 6.875 s |
| `test_xbe_patch_memory_writes.py` | 75 passed, 296.896 s |
| `test_xbe_patch_cave_references.py` | 87 passed, 383.367 s |

All 238 tests above passed without skips. `git diff --check` also passed.
The largest measured test-process peak RSS was 723,860 KiB, below 2 GiB.

The targeted reservation-freshness command is:
`python3 tests/mod_editor/test_nfl2k5_cave_oracle.py CaveOracleTests.test_retail_current_stack_owns_every_supplied_cave_and_runtime_flag`.
It reports the expected single error:
`stale reservation source: mod_editor/core/nfl2k5_franchise_practice.py; regenerate manifest`.
The manifest is protected by this brief. **Claude must regenerate it with
`tools/nfl2k5_cave_oracle.py manifest` after integrating this owner.** Do not
hand-edit its fingerprint. This is an explicit integration requirement, not a
passing freshness check. The existing full cave reservation covers the code;
the new hook is five pinned live instruction bytes, not another cave.

Only bounded executable/synthetic data was read. No disc or pack copy was
created. Root free space was approximately 101 GiB; scratch was 96 KiB.

## Noah's required played witness

1. Build afresh from pinned retail with the existing Experimental preset and
   this correction. Record build/XBE hash and use a disposable franchise save.
   Record week, next opponent, wins/losses, active/reserve membership and a
   recognizable depth-chart order.
2. Open Practice from Coach's Desk. Check Full Scrimmage, the coached teams,
   practice field, Team Select/controller assignment and both sides' controls.
   Run several offensive and defensive reps.
3. Pause, open Quit, cancel confirmation, choose Cancel, then Resume. Verify
   the same rep/session continues. Pause again, accept Quit and verify a usable
   **Coach's Desk**, with normal graphics, menu sounds and controls.
4. Check week/opponent/record, roster, reserves and depth order against step 1.
   Enter and quit Practice again. Open Schedule and Practice Squad afterward.
   Repeat for Special Move and Offense Only, including changing practice
   settings during the session and quitting afterward.
5. Advance one week through the normal franchise action. Verify exactly one
   legitimate progression, normal next opponent and usable Desk. Save, exit,
   reload and verify persistence. Exercise a scheduled Franchise game's normal
   postgame return on a separate test save.
6. Control: Practice entered through retail Game Modes must still return to
   its normal Main Menu. Check its cancel/resume and Rematch behavior. Record
   any unexpected destination, freeze, scene/audio defect or franchise change.

## Delivery

Delivered on `astra/r63-practice-exit-v2` with explicit-path staging and commit
of the owner, its two updated test files, the new v2 route test and this report.
`ASTRA_BRIEF.md` and `.scratch/` are excluded. No push. The protected manifest
regeneration and Noah's played witness remain the integration handoff above.
