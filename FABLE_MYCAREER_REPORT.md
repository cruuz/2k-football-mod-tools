# MyCareer: the Game Modes row and any position

2026-09-07, branch `fable/r63-mycareer`, base `1749663` (beta-62 stack).
**EXPERIMENTAL / UNWITNESSED.** No Xbox boot, played game, rendered screen,
audio or console save was witnessed. Every claim below is labelled:
**PROVED** means bytes decoded from the pinned USA `default.xbe`
(SHA-256 `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`),
corpus data flow read in `research/functions/nfl2k5`, or bounded x86
execution under Unicorn on the installed executable; **HYPOTHESIS** is
everything else, including all on-field behaviour. No emulator, GUI display,
network or push was used; no disc image was built (the main drive sat at the
100 GB floor).

## What Noah asked for and what this delivers

"Get MyCareer working in the next beta, replacing First-Person Football as an
option, and letting you be any position."

| Ask | Delivered | Status |
| --- | --- | --- |
| MyCareer where First Person Football was | The Game Modes row 1 (`0x501494`) is the MyCareer action. The route from the retail list dispatcher through the row's kind-9 case to the owner's `entry`, its native dialog and the native Load / Save push is executed under Unicorn. A build without a sealed setup shows a native message and pushes nothing. | PROVED offline; unwitnessed on hardware |
| First Person Football still reachable | Its Game Modes exhibition entry is gone (the Team Select descriptor `0x526948` has no other reference). The Franchise Settings row at `0x500B24` (label `0xE7D5C4` "First Person Football|TM|", getter `0x147E60`, setter `0x147E80`, Off/On lookup `0x148960`) keeps toggling the same flag `[0xE5FFE4]`. | Row PROVED; the toggled franchise experience HYPOTHESIS |
| Any position | `prepare(position=...)` takes any of the 17 retail codes; the runtime identity compares the record's position with the sealed recipe (checkpoint byte 149) instead of a fixed QB; templates follow the position; a once-only starter lock places MyPlayer on depth row 1 with the depth-lock rank bit. | Writer and identity PROVED; playable-at-position HYPOTHESIS per group below |
| Keep everything composing | Same `8192 RX / 4096 RW` request; template 4,896 bytes (6,176 with the seed); all owner tests, both gates and the pairwise suite: see the results table. | PROVED offline |

## A. The menu route (PROVED bytes and bounded execution)

### Descriptors and rows

Main Menu descriptor `0x515660` (title `0xE8B1CC` "Main Menu", handler
`0xF3E90`, rows `0x5154C0`, screen ID 2); Game Modes descriptor `0x5015CC`
(title `0xE7D664` "Game Modes", handler `0xF3E90`, rows `0x501460`, screen ID
`0x11`). Rows are 0x34 bytes: `+0` kind, `+4` label, `+8` target descriptor,
`+0x28` action callback, `+0x2C` per-frame callback (`0x14FC60` calls it
when non-zero). Kind 3 ends the table.

| Game Modes row | VA | Retail | Label |
| --- | --- | --- | --- |
| 0 | `0x501460` | kind 0 -> `0x500DC8` | `0xE7D5B0` "Franchise" |
| 1 | `0x501494` | kind 0 -> `0x526948` (Team Select, FPP enter `0x2C1FC0`) | `0xE7D5C4` "First Person Football|TM|" |
| 2 | `0x5014C8` | kind 0 -> `0x529AE0` | `0xE7D5F8` "ESPN25th Anniversary" |
| 3 | `0x5014FC` | kind 0 -> `0x529344` | `0xE7D624` "Practice" |
| 4 | `0x501530` | kind 0 -> `0x501298` | `0xE7D638` "Situation" |
| 5 | `0x501564` | kind 0 -> `0x501434` | `0xE7D64C` "Tournament" |
| 6 | `0x501598` | kind 3 | terminator |

The Crib row of the Main Menu (`0x515528`: kind 9, action `0x24D440`) is the
retail precedent for a kind-9 action row; `0x24D440` calls `0x1423B0`, keeps
ECX in ESI and tail-jumps to `0x6E390` with EDX = `0x524FA0`.

### The dispatcher (PROVED, `0x150020`, not a corpus function; Capstone)

`0xF3E90` is the shared handler; its event 6 branch calls `0x150020(ECX =
screen stack)`. Inside, for each of eight ports, when the accept mask
`((~descriptor[+0x28] & 0x40) | 0x400) >> 2` intersects the pressed mask:

```
0015018c  mov [esi+0x594], edi          ; esi = list state ([stack+0x10C]), edi = port
00150192  mov ecx, [ebp+4]              ; ebp = top stack slot (0x6E630): +4 = cursor
00150195  imul ecx, ecx, 0x2c
00150198  lea eax, [ecx+esi]
0015019b  mov ecx, [eax+0x14]           ; state entry +0x14 = row pointer
001501a2  mov edx, [eax+0x1c]           ; +0x1C != 0: disabled
001501a9  mov edx, [ecx]                ; row kind
001501ab  movzx eax, byte [edx+0x15024c]; kind -> case: 0,1,2,2,2,2,2,2,2,3
001501b2  jmp [eax*4+0x15023c]
```

Case 0 (`0x1501D5`): `0x6E390(ECX = stack, EDX = [row+8])`, push the target.
Case 1 (`0x1501FA`): `0x6E2E0`, pop to the target. Case 3 (`0x15021F`):

```
0015021f  mov edx, [ebp+4] ; imul edx, edx, 0x2c ; lea eax, [edx+esi]
00150228  mov esi, [eax+0x14]           ; row
0015022b  lea edx, [eax+0x10]           ; the state entry
0015022e  mov ecx, ebx                  ; the screen stack object
00150230  call [esi+0x28]               ; the action
00150233  pop edi ; pop esi ; pop ebp ; pop ebx ; add esp, 0x10 ; ret
```

So an action receives ECX = the screen stack object, EDX = its state entry,
no stack arguments, and must preserve EBX/EBP/ESI/EDI. The MyCareer `entry`
keeps that: `pushad/popad` around the seed check, `push ecx / pop ecx` around
the dialog, then either `ret` (unconfigured) or a tail `jmp 0x6E390`, whose
own `ret` returns to `0x150233`.

### The dialog and the push (PROVED)

`0x14E440` is `ret 0x18` (six stack words) and forwards to `0x14E070`, whose
prologue pushes EBX/ESI/EDI (`0x14E079..0x14E082`) and epilogue pops them
before `ret 0x28` (`0x14E385..0x14E389`); it is the modal message loop used
by 142 retail callers (for example the FPP controller-count message in
`0x33BFB0`, with the same descriptor `0x5042FC`). `0x6E390(ECX, EDX)`
increments `[stack+0x100]`, stores EDX at `[stack + depth*8]`, sends
descriptor events 5, 1 and 3 through `0x6E4E0` (`ret 4`) and sets
`[stack+0x108] = 1`; it refuses when the depth is already 0x20.

### The installed edit (unchanged from the MVP, now proved end to end)

`entry_kind 0x501494: 0 -> 9`, `entry_label 0x501498: 0xE7D5C4 -> mode_text`,
`entry_target 0x50149C: 0x526948 -> 0`, `entry_action 0x5014BC: 0 -> entry`.
Both `mode_text` (row label) and `title_text` (dialog title) are the 20-byte
`nfl2k5_modern_naming.career_text("menu_row")` /
`career_text("screen_title")` bytes ("MyCareer"), pinned by
`test_menu_and_title_labels_equal_the_naming_owner_contract`.

### Bounded execution (`tests/mod_editor/test_nfl2k5_my_career_unicorn.py`)

A synthetic screen stack (`depth 2`, top `0x5015CC`, cursor on row 1, list
state with the six retail row pointers, `[0xBD8050] = 1`) runs `0x150020`
natively on the installed executable with only the external services stubbed
(port connected, accept pressed on port 0, no d-pad, descriptor event send,
the modal dialog, the dispatcher tail). Results:

- `test_game_modes_row_dispatches_to_entry_dialog_and_load_save`: the kind-9
  case reaches `entry`; the live state equals the sealed setup with phase
  LOST, club -1 and error 7 (the pairing is pending); `[state+2580] = 1`; one
  dialog with ECX `0xE3C040`, EDX `title_text`, arguments
  `[0x5042FC, 0, entry_help, 0, -1, 0]`; the native push leaves
  `[stack+0x100] = 3`, `[stack+24] = 0x508DF0`, `[stack+0x108] = 1`;
  EBX/EBP/ESI/EDI return unchanged; the stack is balanced.
- `test_retail_row_bytes_push_team_select_and_neighbours_keep_their_targets`:
  with the four retail row words restored in memory the same harness pushes
  `0x526948` with no dialog, and rows 0, 2, 3, 4 and 5 push
  `0x500DC8`, `0x529AE0`, `0x529344`, `0x501298`, `0x501434`.
- `test_unconfigured_build_explains_itself_and_pushes_nothing`: an
  `apply(retail)` without a setup shows `no_setup_help` under the same title,
  leaves the depth at 2, `[state+2580] = 0` and the RW state all zero.

What the pairing does after Load / Save is the MVP's path (save read hook
`0x1D8D2` with `[state+2580] = 1`, checkpoint pairing, `load_complete`), all
still covered by the existing thirteen native tests.

### First Person Football after the change

**PROVED:** `[0xE5FFE4]` is written by the FPP enter event (`0x2C1FF1`), the
Franchise Settings row setter `0x147E80`, the settings reset `0x148C60`,
clear `0x148CB0` and `0x2C0AF0`; it is read through `0x627E0` (24 call
sites: coach-mode override `0x63810`, camera `0x7A230..0x7D7A0`, `0xA5620`,
HUD/route setup `0x14C99C..0x14CCB3`, `0x260AA0`) and the 70-caller
predicate `0x627C0`. **HYPOTHESIS:** toggling the Franchise Settings row on
gives franchise games the FPP camera/HUD behaviour those readers implement.
The exhibition-style forced flow (`0x2C1FC0`: mode 4, FPP flag, team select,
flow type 7) is not reachable from any menu after this change; that is
accepted because the row was the only reference to `0x526948` and the flag
survives in Franchise Settings.

## B. Any position

### Writer (PROVED by `test_nfl2k5_my_career.py`)

`prepare(payload, first=, last=, position=, template=, port=, camera=,
starter_lock=, token=)` accepts a position name or code (`rr.position_code`),
picks the first primary-pool prospect with that position byte (`+0x35`),
prospect flag `+8 & 0x10`, no club and not in the free-agent list, renames
him, applies the chosen retail create-a-player template (table `0x5561B8`,
36 x 0x74, three variants for QB K P WR CB FS SS HB FB TE OLB ILB; the apply
routine `0x343460` semantics: `-1` becomes 75) or keeps the generated
ratings, sets years pro 0, keeps the prospect bit and seals the 84-byte
record as the recipe (checkpoint 96..179). The setup JSON is schema
`nfl2k5_my_career/v2` with a `position` label that must agree with the sealed
byte. All 17 codes are exercised; C, G, T, DT and DE refuse a template index
because the retail table has none for them.

### Runtime identity (PROVED by Unicorn)

`primary` compares the live record's `+0x35` with checkpoint byte 149
(`mov cl,[state+149]; cmp [eax+0x35],cl`), so a WR setup binds a WR and
loses identity when the byte changes
(`test_identity_follows_the_recipe_position_for_a_wide_receiver`). Every
other identity fact (name pointers, college, birth word high bits, ordinal)
is unchanged.

### Starter lock (PROVED write; HYPOTHESIS effect)

At the first `resolve_team` that finds MyPlayer on a club's active list the
owner writes `depth_rank` bits 10..12 of `+0x28` to 0 (row 1) and sets
`+0x52 & 1`, once (`[state+184]`). With `nfl2k5_depth_locks` installed the
weekly stage "reserves locked rows ... locked values are untouched"
(ASTRA_DEPTH_LOCKS_REPORT), so the row survives the ratings sort and the
displaced starter takes the next free row. Without that owner the bit is
inert and the row is only an initial placement that the retail weekly sort
may undo. Whether the CPU's personnel packages put row 1 on the field for
every formation is HYPOTHESIS. `starter_lock=False` writes nothing
(`test_starter_lock_writes_depth_row_one_and_rank_bit_once`).

### Control model per position

**PROVED data flow:** the frame input walk `0x1563F0` decodes input for every
on-field entity (`+0x48 == 0`) whose controller block (`entity+0xC`, blocks
`0xBD8210` stride 0x24) has an ID other than -1, through `0x1211E0` and
`0x120A20`; the port's command context is the block's own context word
(`block+4`), applied by `0x1565F0` -> `0x120880` (`[0xA9B960 + port*0x2C]`),
which each body's behaviour sets for itself (sixty call sites of `0x1565F0`
with constants 0..0x11). Command tables live at `0xA99EC0` (three layouts x
21 contexts x 27 commands). The MyCareer binder therefore never chooses a
context; it only pins the human port to MyPlayer's body and re-applies the
body's context (`rebind` -> `0x1565F0`), which is what makes binding
position-agnostic.

Contexts read from layout 0 (command IDs, PROVED bytes; meanings inferred
from retail consumers are HYPOTHESIS): 2 = kick meter (`0x37..0x3B`,
`0x3D/0x3E`); 3 = pre-snap offense with snap (`0x33/0x34/0x8E`, `0x98`);
4 = minimal pre-snap (`0x03`, `0x98`); 8 and 10 = ball carrier (`0x1A`
hurdle, `0x1B` spin, `0x23` truck, `0x18/0x19` stiff-arm, `0x21/0x22` juke,
`0x24..0x2B` right stick); 16 = defender (`0x12..0x15`, `0x06..0x09`);
13 = no commands; 17..20 = coach and play-call menus.

| Group | Templates | PROVED | HYPOTHESIS (until Noah plays it) |
| --- | --- | --- | --- |
| QB | Pocket / Scrambling / Balanced | binding, identity, camera focus, ledger; retail human QB contexts 3/9/10 | the CPU-called play waits for MyPlayer's snap; passing icons and scramble are retail |
| RB (HB, FB) | Finesse/Power/Balanced HB; Blocking/Catching/Balanced FB | binding; retail ball-carrier contexts 8/10 after the handoff | before the handoff MyPlayer must reach the mesh point himself |
| WR | Speed / Hands / Balanced | binding; ball-carrier contexts after a catch | route running and the catch before the ball arrives are the body's own context, unwitnessed outside First Person Football |
| TE | Catching / Blocking / Balanced | as WR | as WR, plus blocking assignments |
| OL (C, G, T) | none: generated ratings kept | prospect replacement, identity, camera | blocking stays the body's behaviour; stick input may only steer him |
| DL (DT, DE) | none: generated ratings kept | binding; retail defender context 16 | rush moves and shed every play |
| LB (OLB, ILB) | Run Stop / Coverage / Balanced | binding; defender context 16 | coverage drops and blitz paths every play |
| DB (CB, FS, SS) | Cover / Physical / Balanced | binding; defender context 16 | coverage, swat and interception every play |
| K / P | Kicker / Punter | binding; kick-meter context 2 | the CPU calls the kick; MyPlayer only sees the field on kicks and punts |

Off the field (`+0x48 != 0`, or MyPlayer's unit not on the field) `rebind`
detaches the port and every other body keeps its CPU callback (existing
`test_bench_injury_duplicate_and_cycle_detach_without_guessing`). The
team-level human flag (`team+0x30`, set by the retail assign `0x156870`,
replaced by `rebind` while MyCareer is enabled) stays clear, which is the
MVP's CPU play-calling design; the play-call screen behaviour for a team with
no human flag is HYPOTHESIS.

### What is still not possible, and why

- Human route running, blocking and pre-handoff control are not retail
  non-FPP features. The FPP flag readers found are camera, HUD/route
  indicator, coach-mode override and controller-count validation; none is a
  body-control rule this owner could switch on. Making a receiver's or
  lineman's context human-driven without the FPP camera is new engine work.
- Snap-to-next-appearance simulation is unchanged from the MVP: only whole
  fixtures are simulated, and never MyPlayer's own.
- The release manifest must be regenerated on a machine with room for its
  disposable disc (WIRING.md); the default JSON pins the two changed source
  files and, at this base, already carries the stale camera span that makes
  the cave-references gate refuse before any owner check (section C).

## C. Composition

Requests unchanged: `(("nfl2k5_my_career","code",8192,16),
("nfl2k5_my_career","data",4096,16))`; budget plan PASS with 54,800 RX,
4,096 RW and 8,616 RO bytes available to new owners. The template is 4,896
bytes plus the 1,280-byte seed; the remaining RX bytes stay `0xCC`. RW use is
unchanged (byte 3,311 of 4,096). No protected file was edited; the
capability JSON in `docs/` was updated and validates semantically when
merged into the registry.

| Command | Result |
| --- | --- |
| `python3 tools/nfl2k5_my_career_assemble.py --check` | template verified |
| `python3 tests/mod_editor/test_nfl2k5_my_career.py` | 13 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | 18 passed |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_my_career_panel.py` | 4 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | 2 passed; 1 refusal that predates this branch (below) |
| `python3 -m tests.mod_editor.test_nfl2k5_practice_reserves` | 9 passed |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | PASS, 41 requests |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 79 passed, both orders, 301.7 s, peak RSS 315,268 KiB; setUpClass asserts MyCareer applied in the composed XBE |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | all four classes refuse in setUpClass on the base manifest (below); 214.2 s, peak RSS 415,180 KiB |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 77 passed (66 pairs both orders + 11 focused MyCareer/playlist/Practice Squad cases), 436.9 s, peak RSS 179,904 KiB |
| `git diff --check` | clean |

### The two refusals that are not this change (PROVED)

- **Cave-references gate and `test_allocation_projection...`.** Both call
  `tests/nfl2k5_allocator_stack.manifest_for_allocated_union` on
  `data/nfl2k5_cave_reservations.json`. That helper refuses when a grown span
  of the manifest has no containing allocation in the manifest's *own*
  `allocator_layout`; the check reads only the manifest. The protected JSON
  at `1749663` carries a stale `nfl2k5_camera` span `0x14DA400..0x14DA440`
  ("declared edit: owned_camera_wrappers") next to the real one at
  `0x14DA830..0x14DA870`; its layout lists the camera allocation only at
  `0x14DA830` (va 21866544). The previous manifest (`75bbd8b`) has the same
  stale span. The MyCareer allocation in that layout (code `0x14DCE70`, data
  `0x14F3200`) equals the current plan exactly. Refusing here is correct
  behaviour and was not weakened; the fix is the release manifest
  regeneration in WIRING.md.
- **The recorder** (`test_nfl2k5_guardian_manifest.py`, the private-evidence
  route the compose session used) raises `invalid declared reservation from
  nfl2k5_xbe_space` in the allocator's own observe step, before any owner
  runs. Re-run at the untouched base with my ten paths stashed
  (`.scratch/fable-mycareer/logs/recorder_base.log`): identical error. Its
  `mapping_end` is the retail image end, which cannot hold the scale-out
  reservations.

The memory-writes gate (79 tests, both orders) and the pairwise suite (77
tests) are the composition evidence this change can produce at this base.

## Noah's witness list

1. Game Modes: MyCareer sits where First Person Football was. In a build
   without a setup it only explains itself; in a configured build it opens
   Load / Save. Check the label, the dialog and that Back returns cleanly.
2. Franchise Settings: First Person Football still toggles and changes the
   game as before.
3. Create MyPlayer at QB, HB, WR, TE, an OL spot, a DL spot, LB, DB, K and P;
   import each paired save, finish the native draft and signing; compare the
   draft log, club, depth row (row 1 with the starter lock; note the displaced
   starter's new row with Depth Locks on and off) and the identity after a
   cold reload.
4. For each position: what the sticks and buttons do before the snap, during
   the play and after the whistle; whether the CPU snaps, calls plays and
   kicks; whether input ever moves to another body; whether the camera
   follows MyPlayer on the other unit's plays and while benched.
5. Everything in the MVP list (ASTRA_MY_CAREER_REPORT.md items 3 to 11).

## Delivery

Explicit-path staging and commit on `fable/r63-mycareer`; no push. The
`.scratch/` directory (research helpers, logs, the observed evidence) is not
committed. Changed paths: `tools/nfl2k5_my_career.S`,
`mod_editor/core/nfl2k5_my_career.py`, `mod_editor/core/nfl2k5_my_career_code.py`,
`mod_editor/gui/my_career_panel_qt.py`, `tests/nfl2k5_my_career_fixture.py`,
`tests/mod_editor/test_nfl2k5_my_career.py`,
`tests/mod_editor/test_nfl2k5_my_career_unicorn.py`,
`tests/mod_editor/test_nfl2k5_my_career_panel.py`,
`docs/mod_editor/nfl2k5_my_career_capabilities.json`, `WIRING.md`,
`FABLE_MYCAREER_REPORT.md`.
