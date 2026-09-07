# Franchise Auto Save, r63

2026-09-07. **EXPERIMENTAL / UNWITNESSED.** No emulator, GUI, audio,
network, physical save, disc build or push was performed.

## Delivered behavior and decisions

`nfl2k5_franchise_autosave` adds an optional native Franchise save after a
completed played or simulated game returns to Coach's Desk. It replaces the
First Person Football rows in Franchise setup and Coach's Desk -> Options ->
Franchise Options with **Auto Save**, using the same native **Off / On** choices.
Both rows address the same owned switch. Generic Game Options has nine occupied
rows and no proved spare; no extra generic Options row was invented.

The installed switch starts Off. Build preset handoff: Basic off, Advanced on,
Experimental on. Those presets install the feature; the player still chooses
On in the game. The setting is restored from the original FPF word in a native
Franchise save, without growing the save or changing its signing/container code.

A successful manual Save Franchise or Load Franchise establishes the current
device and full save name. Auto Save enumerates again and finds that exact
device, name and Franchise type before calling the native Save action. It does
not retain a stale menu ordinal, invent a save name, select an unrelated file,
or pick the first storage device. A new franchise therefore needs one manual
save. If there is no known destination, or the destination disappears, the
game's notice UI explains that a manual save is needed.

Completed results set a pending bit. Saving waits for two quiet updates of the
topmost Desk after game teardown and return animation. Multiple simulated
results before one return to Desk produce one save of the latest state. Saves
are synchronous through the game's own UI and transaction: overwrite and success
confirmations are suppressed only for an active automatic attempt; the retail
progress and error dialogs remain. There is one attempt per pending result,
with no repeated failure popup every frame. Off clears pending work.

Protected product files were not edited. The complete dispatcher, BuildPlan,
preset, UI, packaging, registry-merge and release-manifest handoff is appended to
`WIRING.md`. The standalone owner and CLI, assembly source/generator, capability
object, budget fixture, manifest builder registration and both XBE gate unions
are implemented here. Studio does not expose the new build option until Claude
applies that protected handoff.

## PROVED input and allocation

Evidence: the user-owned USA Xbox `default.xbe`, 11,948,032 bytes, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`,
at `/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe`.
Native instructions/data were inspected with Capstone and the read-only Ghidra
corpus. Existing ASTRA reports, RC85 facts and the hub Franchise save memo were
read; executable bytes take precedence over older address/mode annotations.

| Allocation | Request | Use |
| --- | ---: | --- |
| RX | 1,536 bytes, alignment 16 | 1,027 bytes of assembled code, `CC` padding |
| RW | 128 bytes, alignment 16 | switch, pending/busy flags, slot identity, quiet tick, counters |
| RO | 512 bytes, alignment 16 | fixed UTF-16 label and three native notice strings |

All storage is reserved by `nfl2k5_xbe_space` v3. No runtime data is placed in
`.text`; no retail cave is allocated. Ten complete native instruction spans
total 54 bytes. One existing Desk callback pointer and ten existing menu-row
pointers add 44 bytes, for **21 live edit spans / 98 pinned bytes**. Status pins
33 prerequisite ranges, both recognized Desk-list layouts, each edited span,
the exact code/text templates, zero initialized RW and the allocator seals.
Mixed/foreign bytes refuse before allocation or mutation. Apply/replay is
idempotent, digests are repinned, and receipts include changed-byte counts,
before/after hashes, live edits and owned reservations.

The committed budget fixture plans **44 requests**, resulting XBE size
**12,300,288 bytes**. Its remaining free totals are 54,505 RX, 6,790 RW and
8,104 RO bytes; the allocator reports 4,096 RW bytes still available to new
owners before alignment. This uses 128 bytes of the new owner's spare RW
budget. No allocator geometry was extended by this change. A standalone apply
changes/appends 353,386 bytes including the allocator and section seals.

## PROVED native setting and mode corrections

The brief called `0x147E60` / `0x147E80` a getter/setter pair. Retail shows that
**both are left/right togglers**. The getter is `0x147EB0`; display is
`0x148960`. Row `0x500B24` retains max/min `0x147EC0` / `0x147ED0` and the native
Off/On choice builder `0x147EE0`. The Options row is `0x52BB68`, originally
getter `0x2C6EC0`, left/right `0x2C6E80` / `0x2C6EA0`, display `0x2C74D0` and
choice builder `0x2C6EF0`. Only their label/getter/left/right/display pointers
change. The shared retail value string table is `0x4ED994`.

Native league `[0xE576A0] == 2` is Franchise; **1 is Tournament**. The native
save action chooses type 9 for Franchise, 8 for Tournament, 7 for Exhibition.
Older practice-related notes using league 1 were not copied into this guard.

`[0xE5FFE4]` is a live FPF flag with real loader/gameplay consumers. Merely
renaming the row and leaving that flag On would still activate FPF behavior.
The switch therefore lives in owned RW while using exactly the original saved
word at offset `0x64` of settings prefix `0xE5FF80` (length `0x2E0`):

* At `0x16E4B6`, wrap only the on-disk settings copy call to `0xE2E10`. Execute
  the native copy, then replace destination `+0x64` with the owned switch for
  Franchise. All other settings bytes and native temporary snapshots remain.
* At `0x16E7C5`, after native load copied the settings and camera, recover the
  switch from the same word, clear live FPF, then execute `0xA5460`. This is
  restricted to metadata type 9; Tournament/Exhibition loading keeps retail
  FPF behavior. It does not occupy the camera owner's `0x16E7B1` hook.
* At native league selection `0xC7570`, invalidate the previous slot and clear
  live FPF when selecting Franchise, replaying both original branch paths.

The two Franchise FPF controls are removed. Native FPF consumer routines are
retained because they still serve other game modes; no unsupported deletion of
their code is necessary. MyCareer's separate Game Modes row `0x501494` is not
changed. A standalone Auto Save build does not remove unrelated retail FPF
mode navigation. This owner disables its live flag when entering/loading
Franchise and supplies no Franchise control that re-enables it.

Save compatibility decision: importing an old Franchise with FPF word 1 enables
Auto Save. Conversely, loading an Auto Save-On franchise in an unpatched retail
game interprets that word as FPF-On. Set Off and save before moving such a save
back to retail. This is the requested reuse of the existing persisted word,
not a new container schema or a claim of identical semantics in retail.

## PROVED completion, return and current-slot route

Played completion: game-end/postgame handling uses `0x6EFE0` / `0x6ED30`, then
the game descriptor's ended-state update `0x64CD0` pops via `0x6E400`.
The game teardown callback `0x64CA0` destroys the game (`0x649C0`, clearing
`0xA83A10`) and calls `0x645D0`. Only settings modes 5, 6 and 7 call season
commit `0xC5D60`; Practice modes 0, 1 and 2 bypass it. `0xC5D60` also ignores
game states 0/1. On a completed game it sets the scheduled fixture state to 3
through `0x1C1C80`, runs stats `0x1356C0` and season updates `0x134140`, then
tail-calls the dirty marker `0xC4BC0` at `0xC5DA9`. That tail is wrapped to
mark pending **after** the native commit.

Simulation: native `0xC7A20` calls simulation `0x10B9C0`, then marks the
fixture complete with `0x1C1C80` at `0xC7B61`. That call is wrapped to mark
pending after its original result. The MyCareer simulation prologue is not
changed, and saving is never invoked inside the simulation callback.

Coach's Desk descriptor `0x522190` points to hook list `0x521EE8`. Its event 6
record is `0x521DC8`, whose kind-1 callback at `0x521DCC` is `0x142DD0`.
The native event dispatcher `0x6E4E0` reaches this record. Auto Save wraps only
the callback pointer and executes native Desk update first. The return path
retains native scene refresh `0x142FB0`, animation setup `0x1427A0` and menu
reconstruction. The hook waits for:

* topmost descriptor `0x522190` and valid native stack depth below 32;
* game scene `0xA83A10 == 0`, no pending Desk destination `0xAA2408`;
* a non-null Desk scene `0xAA2140`, finite nonnegative scene time `scene+4`
  at or beyond the animation target `0xAA2400`;
* idle native I/O controller `0xBDBDB0 == 1` and operation state `0xBDBDA0`
  equal to 0, 7 or 8 (7/8 are completed-load navigation states);
* switch On, league 2, pending result, and no active automatic attempt.

The animation target is not assumed to be zero: the tests exercise 3.0 seconds.
Another quiet update is required after a blocked transition clears. A busy
flag covers native progress/error rendering, whose event pumping may reenter
Desk. Original callback registers, flags and stack effects are preserved.

Franchise Practice moves the entire Desk hook list into its cave and reuses
the original span for a row. Recognition accepts that exact list only after
the whole Practice installation validates. Likewise the music playlist's
five-byte `0x6E4E0` dispatcher prologue is accepted only through its complete
owner status; all remaining native dispatcher bytes stay pinned. These are
specific composition contracts, not arbitrary foreign-byte exemptions.

Successful native load reaches `0x16E81A` after season and front-office
deserialization. EBP is the selected metadata byte offset, not a UI ordinal.
The wrapper captures a type-9 full UTF-16 name (up to 16 code units) and device
identity. `0x16E540` invalidates the old identity before any new load attempt,
including one that fails. Native successful save also captures its destination.

On an attempt, `0x16BB20` performs native discovery. The owner finds its saved
device among the nine native records (stride `0x34`), selects/enumerates through
`0x16B740`, then matches type 9 and the complete saved name in metadata
`0xBDC1C8` (stride 24, at most 256 rows). It invokes `0x16E3F0` with the found
ordinal in ECX. Native session storage originates at startup `0x16B060`
(caller `0x748A0`); no separate controller allocation is invented. The native
session closes through `0x16A640`, and the previous manager pointer
`0xBDBDA4` is restored on exit.

## PROVED manual Save and native signing reuse

Desk Options `0x503458` -> Load/Save `0x508F8C` -> Save Franchise row
`0x508E20` -> descriptor `0x507EC8` is retained. Its list uses the existing
native table `0x506700`; the Save action callbacks at `0x504C50` / `0x504C68`
point to **`0x16E3F0`**, the routine Auto Save calls. The descriptor's event-1
record `0x507DE8` calls the same native discovery `0x16BB20`.

`0x16E3F0` obtains native Franchise size/type and invokes preflight `0x16BE80`,
allocates a buffer, serializes settings (`0xE2E10`), camera (`0xA5470`), roster
(`0xC1F90`), season (`0xC5310`) and front office (`0x2D0790`), then calls
transaction **`0x16C2F0`**. Sizes and all serializers remain native.

Only the overwrite confirmation CALL at `0x16C03E` is bypassed during Auto
Save, returning native answer 2. The dialog takes six stack arguments and uses
`ret 24`. Native delete `0x3B4B0`, create `0x3AF30`, write `0x3B340`, close
`0x3AE10`, enumeration and same-name/type/size completion checks all remain.
Only after those checks does `0x16C50D` reach the success-dialog wrapper.
Manual overwrite and success dialogs still run. Native progress calls retain
callback `0x16A7A0`; failure mapping/dialog/reset remains `0x16BD70`.

Signing remains below those native APIs: `0x3B340` submits the native queued
write through `0x3A1C0`. The retail storage provider contains write `0x4D720`,
signature update `0x4D520` -> `XCalculateSignatureUpdate` at `0x1FE33`, begin
`0x4B2A0` -> `XCalculateSignatureBegin` at `0x1FE1F` with mode 0, and finalize
`0x4C880` -> `XCalculateSignatureEnd` at `0x1FE81` plus the native 20-byte
signature write. Those routines are byte-pinned and unchanged. This establishes
reuse of the game's save/signing implementation; it does **not** constitute a
physical signed-file or kernel-I/O witness. There is no custom container,
signature calculation, Xbox filesystem writer or host save-file mutation.

Native allocation failure after overwrite preflight ordinarily returns silently.
The isolated allocation CALL at `0x16E4A9` is wrapped to show a native notice
only when an Auto Save attempt cannot allocate its buffer. Ordinary native I/O
failures continue through the real failure handler. The underlying retail
overwrite deletes before writing; this feature does not make that transaction
atomic or protect against storage loss or interruption during the save itself.

## PROVED tests and explicit test limits

All feature tests are standalone `unittest` programs; missing retail evidence, Capstone or Unicorn
causes the relevant precise skip. The bounded machine maps the XBE and allocator
with real permissions, checks every top-level return stack, caps execution at
200,000 instructions and releases each machine between scenarios.

The native suite executes actual played commit, practice teardown mode guard,
post-simulation result code, both installed menu rows, native settings copy,
Desk event dispatch/update in both list layouts, `0x16E3F0` / `0x16BE80` /
`0x16C2F0`, actual native failure handler and reload type dispatch. It covers
Off, Tournament, absent slot/device/name, changed ordinals, ninth device,
overlong names, excessive metadata count, active saves, load states, missing or
busy Desk/scene, NaN/negative scene times, repeat updates, all four I/O failure
stages, allocation failure, and preservation of native registers/flags/stack.
An automatically serialized buffer is loaded in a fresh machine through the
real native load dispatch/settings copy; a failed load invalidates its old slot.

Storage/OS completion, rendering/controller services, device enumeration,
unrelated roster/season/front-office serializers and scene resource allocation
are explicitly substituted in `tests/nfl2k5_franchise_autosave_fixture.py`.
They bound execution and supply success/failure outcomes, not physical saves.
The tests do not boot the Xbox title, run a complete football simulation,
authenticate a physical container, or prove that the menu looks right on screen.

Final commands and results (run from this worktree):

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_franchise_autosave.py` | PASS, 7 tests |
| `python3 tests/mod_editor/test_nfl2k5_franchise_autosave_unicorn.py` | PASS, 15 tests |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | PASS, 83 tests, 327.751 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | PASS, 99 tests, 415.459 s |
| `python3 tests/mod_editor/test_nfl2k5_camera_far.py` | PASS, 16 tests |
| `python3 tests/mod_editor/test_nfl2k5_franchise_practice.py` | PASS, 22 tests |
| `python3 tests/mod_editor/test_nfl2k5_franchise_practice_exit_v2.py` | PASS, 8 tests |
| `python3 tools/nfl2k5_franchise_autosave_assemble.py --check` | PASS, checked-in template exactly regenerated |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | PASS, 44 requests, no build |
| `python3 -m mod_editor.core.nfl2k5_franchise_autosave status <retail-default.xbe>` | PASS, retail |
| `python3 -m mod_editor.capabilities.validate_registry --skip-file-checks` | PASS, 110 baseline capability objects |
| `git diff --check` and exact protected-file comparison against HEAD | PASS |

Both XBE gates execute forward/reverse and automatic/explicit v3 layouts, with
all owner statuses, replay and byte-equivalence checks. The new gate tests also
check all Auto Save hook instruction boundaries, absence of interior native
entries/foreign ownership, fresh owned regions and writable destinations.

The feature's capability test merges the new object into the existing registry
in memory, validates the entire schema and resolves every new evidence/module/
command reference with the registry helpers. Full baseline file-check mode was
also attempted and fails on the pre-existing missing
`docs/research/apf_audio.md` at capability 0. That unrelated checkout limitation
is not hidden or reported as a successful full-registry validation. The new
object itself is complete and its referenced files are present.

## HYPOTHESIS and Noah's witness list

Native return animation readiness, modal rendering/event reentry, physical
device identity across removals, actual progress text, signed save reload and
long-session stability remain unwitnessed. No runtime-proved claim is made.
The exact failure path depends on native storage services completing; no
independent watchdog replaces the game's own wait loops.

After Claude wires the product and regenerates the release manifest:

1. Build from the pinned base with Auto Save installed. In a disposable new
   Franchise, confirm both replaced rows read Auto Save, show Off/On correctly,
   and change the same value. Verify ordinary menus and Franchise Practice.
2. Turn On, manually save once to a named Franchise slot, and record the name,
   device, week and record. This establishes the intended automatic destination.
3. Play a complete scheduled game. Return through postgame to Coach's Desk;
   watch the retail saving indicator, with no overwrite/success confirmation.
   Verify the Desk returns to normal input and only the chosen slot changed.
4. After saving finishes, force-quit the emulator. Reload that slot and verify
   week, result, roster/front-office state and Auto Save On survived. Do not
   substitute a save-state restore for a real Franchise load.
5. Simulate one game, return to Desk and repeat the forced-quit/reload check.
   Simulate several before one return and verify the latest combined results.
6. Set Off, complete another game and verify no automatic save. Verify manual
   Save still asks its ordinary confirmation, reports success and reloads.
7. Try a new franchise with no saved slot, and a known slot made unavailable.
   Confirm a useful native notice, responsive input and no repeated frame-by-
   frame retry. Exercise safe native full/unavailable-device failure fixtures.
8. Repeat several played/simulated weeks, visit Options/Practice between games,
   cancel a load, and load another Franchise slot. Confirm no stale-slot
   overwrite, no saves while loading/playing/practicing, correct current-slot
   selection and normal progress/error dialog behavior with other owners on.

## Resource and delivery discipline

Only this worktree and bounded scratch receipts/logs were written. The dirty
source corpus and other worktrees were read-only. No disc/archive was loaded
whole into RAM, copied, or built. Root free space was 107,807,916,032 bytes
(above 100 GB); the final pre-delivery check was 107,472,445,440 bytes and scratch
was 100 KiB, below 200 MB. The release reservation JSON, release
tags, CI, packaging runtime checker and all protected GUI/dispatcher files are
unchanged. Explicit-path commit or a scratch bundle is the delivery mechanism;
the brief and scratch contents are excluded from the commit. No push.

Normal explicit-path staging was attempted and refused because the worktree's
shared Git metadata is read-only (`index.lock`: Read-only file system).
Delivery therefore uses the authorized fallback:
`.scratch/franchise-autosave.bundle`, with a commit based on the original HEAD,
created through separate scratch Git metadata and exactly the 15 deliverable
paths. The working files remain in place. Verify with
`git bundle verify .scratch/franchise-autosave.bundle`; the bundle requires the
original base commit already present in the coordinating repository. The brief
and scratch contents are not part of the bundled commit. No push was attempted.
