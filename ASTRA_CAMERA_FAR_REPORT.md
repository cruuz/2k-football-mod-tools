# r63 camera Far: actual selection and raised framing

2026-09-07. Base `f263cd04365f9874541c756958a40b998d405e6d`, branch
`astra/r63-camera-far`. **EXPERIMENTAL / UNWITNESSED.** No emulator, GUI,
audio, network, disc build or archive-pack load was used.

The existing `camera=True` option now selects row **1, Far**, at fresh
settings initialization, Settings/Franchise load and common game-camera
initialization. Seven Far descriptors put the sampled action higher and
farther back. Standard stays retail, and Options remains a session choice.
This replaces the former Standard-descriptor-only patch. There is no new
checkbox. Old installations must be rebuilt from retail.

The core, public fixture, native CPU tests, allocator union, both gates and
manifest builder are complete. The camera-only XBE BuildPlan works. Combined
production builds still need the protected wiring specified in
[WIRING.md](WIRING.md#r63-camera-far-existing-camera-flag-64-rx-bytes-2026-09-07).
Those protected files and the release manifest were deliberately left
untouched as required by the brief. Claude must wire and regenerate them
before an Experimental-preset release or image acceptance build.

## Evidence and diagnosis

The pinned USA `default.xbe` is 11,948,032 bytes, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Only that executable was read from the supplied extraction. The read-only
Ghidra corpus was `/home/noah/2k-football-mod-tools/research/functions/nfl2k5/`.
The corpus's `functions.tsv` and relevant pseudo-C shards were checked
against the actual instructions. The corpus omits some saved-load callers
from its helper cross-references; the executable census below supplies them.

Prior material reviewed: the existing ASTRA report set (65 reports at the
start), RC81/RC82/RC85 changelog sections, CAMERA_MAP, camera inspector and
tests, allocator scale-out, MyCareer and widescreen v3 reports, and the
seven-recipient camera section in `APF_TO_2K5_PORT_RESEARCH.md`. The brief's
`ASTRA_APF_PORT_RESEARCH.md` filename does not exist here; that file is its
relevant equivalent. The retail inspector still reports seven settings and
six menu presets. Its read-only retail contract remains intact.

**PROVED:** the previous patch never selected Far. It replaced geometry in
seven **Standard row 0** records, leaving `E5FFF0` and the active row
`B665F0` alone. Thus a correct old build can still say Standard in Options.
Saved settings can also restore any old camera index. Selecting a different
row bypasses those Standard records. Some retail Standard and Far positions
are identical; changing their lens alone does not raise the backfield enough
to clear this scorebar.

**PROVED:** `66720/66B20` are camera-object constructors, not a late global
Standard-default writer. `60090` copies the selected 80-byte descriptor into
the slot at `A82D30` and invokes its setup callback. Native table lookup,
descriptor copy and setup preserve the revised geometry when optional pass
zoom is off. The Far live callback `A4C30` recopies **Far `A88D20`**, so the
new values also feed its pullback calculation. The optional pass-in-air
callback `A4BF0` does overwrite some geometry when Pass Play Zoom Out is on;
that path is included in the projection proof. There is no evidence that a
constructor silently restores Standard over every patched camera.

**HYPOTHESIS:** Noah's exact earlier build may have used a saved non-Standard
row, an older output, or a state with its own camera. His loaded executable,
save and live row were not provided. These possibilities cannot be ranked
as an observed root cause. What is established is the old implementation's
failure to select Far, plus a reproducible low-backfield projection with
retail Far. This revision fixes those two concrete deficiencies; it does not
claim to have reproduced Noah's emulator session.

## Selection, settings and modes

Addresses in this report are Xbox virtual addresses. The immutable table at
`4F03F8` contains 8 rows, 29 states each, `(flags u32, descriptor pointer u32)`
per entry. The menu exposes Standard, Far, Side, Iso, Blimp, Custom at 0..5.
Internal rows 6 and 7 serve First Person and automatic/presentation cameras;
they are not additional hidden menu choices.

| Decision | Pinned retail behavior and revision |
| --- | --- |
| Fresh settings, `E3B90`, site `E3C68` | Retail stores EDI=0 in `E5FFF0`. Change `33ff893df0ffe500` to `33ff8935f0ffe500`, storing the already initialized ESI=1. EDI remains zero for adjacent defaults. |
| Saved Settings load, `16D1D4` and `16E864` | Calls to `E2E20` now call the owned load wrapper. It performs the complete native copy, then sets only the camera index to 1. |
| Franchise-containing load, `16E7B1` | Uses the same wrapper on the embedded settings prefix before the remaining franchise payload is imported. |
| Common game entry, `64710 -> 64991 -> A55A0` | An unconditional call reaches the common camera initializer. Its final `A55EB` jump now enters the owned wrapper: option=1, native `A5B20(1,1)`, then `A5490`. |
| Live selection, `A5490` | Reads the session option into active row `B665F0`, marks `B665F4` dirty on change. Retail selects row 7 with no human controller; replacing `7e06` at `A54C3` with two NOPs uses the session choice there too. |
| Options, `2C6960` | Remains native: writes `E5FFF0`, calls `A5B20`, updates the descriptor. All six choices remain usable until the next saved load or new game entry. |
| State change, `A572D..A5755` | Native indexing computes `(active_row * 29 + state) * 8` and passes the table's descriptor to `60090`. Tests execute this for Standard and Far across all seven recipients. |

The earlier CAMERA_MAP statement that the retail controller gate requires
*exactly one* human is too narrow: raw instructions branch on count **> 0**.
The eight-controller scan stops early after the second human, but either
positive count still reaches the option read. Only zero humans uses row 7.

The flat settings prefix is 736 bytes at `E5FF80..E6025F`. Offsets within
that prefix are camera `+70`, QB pivot `+74`, runner pivot `+78`, pass zoom
`+7C`, Custom distance `+80`, angle `+84`, height `+88`. The first four are
32-bit option words; the last three are floats. STG and FXG carry this
prefix; each franchise has its own copy. USR/TMM profile data does not carry
these camera fields. These are offsets within the settings prefix, not an
assertion that all container formats put it at the same outer file offset.
Loading existing Standard, Side, Custom or invalid camera words produces Far
in live settings without rewriting the source save bytes or other fields.
The native saver will serialize whatever session value is current; loading
it later selects Far again.

The old module's description of `2C69D0` and `2C6A90` as profile save/load
was incorrect. They snapshot seven words at `C8E1A0..C8E1B8` plus a temporary
camera object at `C8DEF0`, then restore them on menu Cancel. They remain
unchanged, as do the Custom slider callbacks that select row 5.

The executable's E8/E9 census finds `E2E20` calls at `63B95`, `844BA`,
`84D7B`, `16D1D4`, `16E7B1`, `16E864`, `28FA6E`, `28FEBC`. Only the three
saved-load sites are changed. Generic temporary/replay settings copies and
restores remain native; blanket-hooking `E2E20` would incorrectly discard
session choices. The tests execute all three changed calls and the unchanged
generic restore, checking the full 736 bytes, unchanged source, native EAX
destination and balanced stack. Replay setup can initialize a temporary
camera through the common initializer; its original settings snapshot is
retained for the unchanged restore on exit. Full replay transitions still
need a gameplay witness.

`A55A0` has one direct retail caller, `64991` in `64710`. The corpus lists
entry/reinitialization callers of `64710` at `64B10`, `64C70`, `84D60`,
`15D930`, `15DBF0`. Quick Game, Practice and Franchise feed the shared game
settings and this common camera initialization; no separate ordinary camera
default per mode was found. **PROVED within the bounded execution:** mode
words 0..9 and prior active rows 0..7 all end with option and active row 1
when executing the actual `64991` call through the initializer. This is a
proof that the common reset has no mode-dependent escape, not a played tour
of every front-end route.

The separate First Person initializer `7BB40` can select row 6 before the
common camera initialization. The new wrapper uses `A5B20` instead of only
writing the active global: it exits row 6 through the game's existing
temporary audio/pivot restoration. Explicit in-session First Person toggles
remain native. The retail active-setter census also finds `79DE4`, `7BB72`,
`7DA2E`, `7DA47`, `27AEE5`, `27AF34`, `2C697E`; these cover option restoration,
First Person toggles and presentation/Options paths, not independent
Quick/Practice/Franchise defaults.

MyCareer previously selected its setup camera every frame at its existing
`A5490` hook. Its existing assembly now checks the pinned Far-default ModRM
byte at `E3C6B` and follows its normal retail/session path when this camera
patch is enabled. Camera off retains MyCareer's original behavior. Both
apply orders and all six Options choices pass the native MyCareer test.
The MyCareer save structure, setup choices and allocation sizes are unchanged.

## Exact Far geometry

Only `+10..+1B` (target xyz), `+20..+23` (lens) and `+30..+3B` (eye offset
xyz) are writable fields in each 80-byte record. Type, flags, lag pointer,
setup callback, frame callback, padding and other words are byte-preserved.
Every x component stays zero. Values below are centimetres relative to the
camera's focus, with deltas relative to **retail Far**, not Standard.

| State / Far VA | New target (y,z) | Target delta (y,z) | New eye (y,z) | Eye delta (y,z) | Lens |
| --- | --- | --- | --- | --- | --- |
| 9 pre-snap / `A88B90` | (0,-250) | (-175,-450) | (700,-1800) | (+300,-500) | 28 |
| 13 catch / `A88BE0` | (0,-250) | (0,-250) | (650,-1600) | (+450,-800) | 28 |
| 15 pass in air / `A88D70` | (50,-150) | (-50,-150) | (800,-2000) | (+300,-950) | 24 |
| 16 live / `A88D20` | (0,-350) | (-100,-200) | (650,-1600) | (+380,-850) | 28 |
| 17 carrier / `A88C30` | (0,-250) | (-80,-180) | (650,-1600) | (+250,-550) | 28 |
| 18 live / `A88C80` | (0,-250) | (0,-250) | (650,-1600) | (+450,-800) | 28 |
| 19 behind / `A88CD0` | (0,-250) | (-80,-180) | (650,-1600) | (+250,-550) | 28 |

All lens deltas are zero. This word feeds the native lens setter as
`lens / 18`; it is not being asserted to be a field of view in degrees.
The settled pre-snap downward pitch is about 24.3 degrees and live pitch
about 27.5 degrees. Raising the eye and moving the look-at toward the near
ground lifts the focus/backfield on screen while retaining Far's lens.

State 1/preview aliases Far state 16. The table and unrelated state records
are unchanged, including Far states 8=`A88AA0`, 10=`A88B40`, 11=`A88AF0`,
12=`A884B0`. FG, punt and kickoff retain their authored specialized views.
The widescreen v3 audit's kick-camera distinctions are respected; the seven
scrimmage recipients do not justify changing every camera in the table.

The existing backend-only `broadcast_wide` named variant is retained, now
applied to the Far recipients with the same selection policy. `far_look`
remains the default public key and is the variant proved/rendered here.
Neither an old Standard rewrite nor another named variant is accepted as
an exact `far_look` installation.

## Projection receipt and limits

[Native fixture image](docs/mod_editor/camera_far_projection.png) compares
retail Far, revised Far 4:3 and revised Far widescreen v3 for pre-snap/live.
[JSON receipts](docs/mod_editor/camera_far_receipts.json) include all exact
patch bytes, allocation metadata, before/after executable hashes, section
digest updates, selection instruction receipts, the direct-call census,
descriptor deltas and all 54 projection rows.

The proof executes retail `60090`, `66B20/66720`, `2BA10`, `66A90`, `2AC80`
and `2AB40` in bounded Unicorn, using the existing widescreen fixtures.
The actual descriptor copier invokes the actual Far setup callback. The
normalized look-at basis and settled ground focus are explicit host fixture
inputs. Native framebuffer x is normalized from 720 to 640; y stays 480.
The scorebar rectangle is exactly `[84,381,560,429]` in that presentation.

Cases cover both field directions and 4:3, 16:9, 16:10. The seven states
plus pass-zoom-on for state 15 and a modeled doubled live pullback produce
54 cases. The moving live callback is not executed end to end; its two
pullback samples are fixture inputs derived from the inspected callback.
Synthetic ground samples are at focus, 500 cm behind and 700 cm behind.

**PROVED for these inputs:** every focus sample is at least **113.458 px**
above y=381; every 700 cm backfield sample is at least **63.401 px** above
it. The greatest sampled backfield y is 317.599. All tested widescreen y
values match 4:3 within 0.001 px. Normal pre-snap focus y is 216.822; normal
live focus y is 199.203. By comparison, retail Far pre-snap projects the
500 cm backfield sample to y=381.440, directly inside the specified bar,
and the 700 cm sample to y=444.048. Retail live projects the same samples
even lower. That is a fixture reproduction of insufficient clearance,
not a screenshot from Noah's game.

**HYPOTHESIS / still unwitnessed:** these margins will improve actual play
readability. The schematic field/players are not GPU output. Dynamic
focus, smoothing, ball flight, sidelines, pivots, alternate camera states,
split-screen and the full visual result have not been proved by a settled
projection. The new Far may feel too high or too distant in some plays.
No GUI text should label this witnessed on the strength of these fixtures.

## Ownership, safety and integration

`REQUESTS = (("nfl2k5_camera", "code", 64, 16),)` consumes 64 RX bytes:
23 bytes for common entry, 16 for saved load, 25 bytes of CC padding.
There is no new RW/RO request, retail cave, writable code page or allocation
outside the existing grown-section allocator. The brief assigned no camera
budget row; this small RX addition is recorded explicitly in the committed
budget fixture. Existing page counts are unchanged.

The plan with all 41 budget requests passes at 12,300,288 XBE bytes.
After camera, RX has 56,041 free bytes (54,800 available to new owners before
alignment), RW 6,918 free (4,096 available to new owners), RO 8,616 free.
The camera's VA is obtained from the named allocation, never assumed from
this plan or the standalone receipt.

`status` checks valid allocator geometry/digests, whole hook instructions,
immutable surrounding contexts, table and native helper hashes, all seven
untouched Standard records, all seven Far records and the exact owned code.
Mixed, foreign, truncated, old-descriptor-only and wrong-variant inputs refuse
before mutation. A sealed allocator union without camera refuses instead of
claiming free space. `apply` repins changed section digests and verifies
exact applied status; replay returns unchanged bytes and zero changes.

The full owner union includes camera in both apply orders. The cave gate
uses the existing `manifest_for_allocated_union` projection for named grown
allocations because this 64-byte owner shifts later allocated addresses.
Matching requires the same owner, kind, size and alignment; retail
reservations remain intact. The initial stale-address gate failure was
resolved by this existing mechanism, not by treating unknown caves as free.
A pre-existing kickoff check was also corrected to recognize the release
manifest's transfer of its eligibility hook to relocated kickoff; exact
installed-code checks remain. The protected manifest was not regenerated.

The WIRING handoff specifies the dispatcher request union and adapters,
allocator ordering, final tuple, kwarg, four status dictionaries plus grown
status, BuildPlan deferral and final pass, current Basic/Advanced/Experimental
defaults, Retail/Patch text, NEEDS_IMAGE, 34-character caption, retained
allowlist and closure imports, and the absence of a new capability surface.
Combined production builds are not claimed complete before that handoff.

## Validation

Final commands and results on this worktree:

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_camera_far.py` | **11 passed**, 24.499 s, peak RSS 270,084 KiB. Four public synthetic tests plus seven private/native tests. |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | **79 passed**, 300.293 s, peak RSS 314,144 KiB. Both owner orders included. |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | **95 passed**, 387.629 s, peak RSS 503,320 KiB. Both owner orders included. |
| `python3 tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | **13 passed**, 5.528 s, peak RSS 394,448 KiB. |
| `python3 tests/mod_editor/test_nfl2k5_my_career.py` | **7 passed**, 9.194 s. |
| `python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | **3 passed**, 5.892 s; named-allocation projection, retail reservation preservation and owner recording. |
| `python3 tests/nfl2k5_camera_test.py` | **8 passed**, 8.631 s; legacy entry point and retained HUD tests. |
| `python3 tests/mod_editor/test_nfl2k5_widescreen_polish.py` | **13 passed**, 6.046 s. |
| `PYTHONPATH=. python3 tests/mod_editor/test_camera_inspection.py` | **17 passed**, 0.005 s. The existing file's plain standalone invocation fails its root import; no unrelated inspector file was changed. |
| `python3 tools/nfl2k5_my_career_assemble.py --check` | Passed; generated template matches assembly. |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | Passed, 41 requests; allocation only, no build. |
| `python3 tools/nfl2k5_camera_far_proof.py --json docs/mod_editor/camera_far_receipts.json --png docs/mod_editor/camera_far_projection.png` | 54 native projection cases, receipts and schematic rendered with Agg. |
| `python3 -m mod_editor --inspect-camera-options nfl2k5` | Passed, read-only retail report. |

The new camera test runs standalone with plain Python and uses precise
private-XBE/Unicorn/Capstone skips. Its synthetic fixture is at most 12 MB;
only allocator identity pins are scoped to that invented fixture. Camera
instruction/descriptor pins remain enforced. A camera-only BuildPlan test
uses a resolved TemporaryDirectory, verifies source preservation, exact
output equivalence and applied inspection, then removes both XBE copies.
An additional bounded `Recorder.wrapper(camera, "apply")` check captured
all six complete hook spans and the named 64-byte RX allocation, without
creating a disc or regenerating the protected manifest. Compilation,
`git diff --check` and the generated MyCareer assembly check passed.

No process approached the 2 GB test bound or 25 GB outer bound; the largest
observed final test RSS was about 492 MiB. Initial free space was
102,035,636,224 bytes and the late check was 107,942,236,160 bytes, both above
100 decimal GB. Scratch before delivery was under 1 MB, below its 200 MB
limit. No acceptance disc or pack was created or left behind.

## Noah's witnesses and required next play checks

The only gameplay witnesses used are Noah's two reports from 2026-09-07,
xemu, Experimental preset with `camera=True`, under the old caption:

1. "the default camera should always be far, and for whatever reason it's
   always on the regular one when I start the game. It should always be on
   far every single time."
2. "the default camera is too close to the scorebug. We need to kinda raise
   what's happening": the action sits low and the bottom scorebar overlaps it.

This revision has **no new gameplay witness**. After protected wiring and a
fresh build, record the build receipt/hash, mode, loaded settings/franchise,
camera shown in Options and screenshot or short clip for these checks:

1. Cold boot with new settings, then existing STG saved as Standard, Far,
   Side and Custom. Far must be selected after each load. Repeat with an
   existing FXG carrying a different camera and a newly created franchise.
2. Start Quick Game, Practice, a new franchise game and an existing franchise
   game. Exit and start again. Far must be selected at each new entry.
3. During each session, select Standard, Side, Iso, Blimp and Custom in
   Options, accept and resume. Confirm the choice persists through plays,
   pause, menu Cancel and instant replay return. Change a Custom slider.
   The next game/practice must return to Far. Save and reload Settings/FXG
   after choosing another camera and confirm the load reset.
4. In both field directions and 4:3, widescreen 16:9 and 16:10, capture
   pre-snap, handoff/run, pass flight, catch and sideline action. Check the
   LOS, quarterback, deep backfield and ball against the actual scorebar
   and assess whether Far is now too high/distant.
5. Repeat with QB pivot, runner pivot and Pass Play Zoom Out enabled. Check
   rapid play transitions and long pass pullback, not just settled views.
6. Exercise field goal, punt and kickoff states 8/10/11/12 and their return
   transitions. Their descriptors were intentionally not revised; confirm
   native specialized views, camera recovery and scorebar readability.
7. Exercise no-human/spectator starts, multiple controllers, First Person
   Football start/explicit toggle, and MyCareer. All starts should use Far;
   explicit in-session choices should still work, with no First Person
   pivot/audio-state regression. Check split-screen if supported by the mode.

## Delivery

Delivery uses an explicit-path commit on `astra/r63-camera-far`; Git accepted
the explicit-path staging operation in this environment. The commit is
based on the base hash above. `ASTRA_BRIEF.md` and `.scratch/` are excluded.
No protected file is changed. No push.
