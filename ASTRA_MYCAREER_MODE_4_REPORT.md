# MyCareer mode 4

EXPERIMENTAL / UNWITNESSED. Base `aed95b09`, branch
`astra/r64-mycareer-mode-4`. PROVED means the specific byte inspection,
bounded native instruction execution or host check below. Noah has not
played these changes. His two earlier play-throughs remain the only
witnessed gameplay. No emulator boot, GUI display, audio, network or push
was used in this session.

This update draws the Apartment and a real 32-club picker with retail
fonts, restores MyPlayer's indicator, receiver icons and pre-snap art,
keeps abandoned fixtures playable, continues the first Play action into
its own fixture, defaults Team Select to the career club, and separates
pre-lineup camera framing from the existing gameplay focus. The required
CPU wait message is installed. Supersim is not installed.

## PROVED: why the owned lists were blank

The old owned descriptors supplied an animated-list handler, row pointers
and UTF-16 strings without the renderer's corresponding layout resources.
The native menu still constructed its rows and processed input. That is why
blind A presses could run Play while only the backdrop was visible.

`F3E90` dispatches event 7 to `F2810`, `F2F70`, then `150260`.
Its constructor `F3CD0` calls `14FCD0` with EDX zero, writing zero to the
working object's `+A7C` renderer mode. `150260` calls the direct list-text
renderer `14FDA0` only when that word is neither zero nor one. The owned
menus therefore did not reach that text renderer. The animated route
`F2F70` draws through `143DE0` only when working `+5A0` contains a loaded
layout. `F37E0` obtains that resource using descriptor `+18` as a LAYT
resource name and binds descriptor `+1C` through `143EA0`. A pointer to
`Off field: CPU at normal speed` in `+18` is not a drawn footer; it is an
unsatisfied resource lookup. Zero `+1C` also supplies no binding table.

For comparison, retail Coach's Desk at `522190` has row table `521F20`,
resource name `E9A864`, binding table `ACF1A8`, frame bounds
`02400044/018D0052` and flags 7. Game Modes at `5015CC` retains resource
`E7D67C` and bindings `AA281C`. Practice Squad extends the working retail
Desk table and clones the native roster descriptor, frame, sheet and pages;
it does not make an arbitrary string-only descriptor render as a sheet.
The old owned rows were valid 52-byte native records, but the missing
animated binding and disabled direct-text mode prevented their display.
This applies equally to the Apartment reached after Sign and after a game.

The old Choose team entry had an additional input defect: it was a kind-5
settings row. The native A handler `150020` admits kinds 0, 1 and 9; A did
not invoke a club-picker action. It was not evidence that the user had
confirmed the default club.

The fix retains the native event/input/backdrop handler and adds an owned
text pass after event 7. `6BC30` constructs the retail text context, binds
the font, applies native selected-row styling and walks UTF-16 text through
`F1C70 -> 47420 -> 46DF0 -> 46420 -> 46310`. Font pointers come from the
same `A90ECC` slot table used by retail `EF850`: title slot 6, main rows
slot 1, club rows/footer slot 0. The text color is opaque `FFFFFFFF`;
alignment, metrics and glyph vertices are native. No glyph bitmap, shared
skybox, substitute system font or screenshot was created.

The bounded draw proof supplies the pinned retail FONT resource, with its
nine font hashes checked and pointers relocated into a bounded fixture
heap. It executes actual event 7, formatting, context/font setup and glyph
walking. Only immediate GPU submission leaves are substituted. Every
nonblank line has finite glyph vertices inside the 640x480 safe region.
The original `F3E90` descriptor handler is a negative control: the same
Apartment constructs rows but emits zero text. The fixed handler emits the
title, five rows and footer, both before a game and after native quit.
Resource loading itself remains an explicit fixture boundary; this is CPU
draw evidence, not a displayed xemu frame.

## PROVED: club choice and Apartment contents

Choose team is now a kind-9 action opening 32 kind-9 rows plus the native
terminator. All 32 names come from the real ROST team name pointers and
are drawn in two columns of 16. The current selected row uses the retail
selected style; reopening retains the confirmed club. Native Back returns
to creation without signing. Every club index 0..31 is confirmed through
native A/stack handling on both allocation layouts. The final confirmation
signs club 31, and the resulting club roster contains MyPlayer exactly
once. The existing frontend tests independently sign different clubs and
preserve cancellation/rollback and refusal cases.

The Apartment draws exactly:

1. Play next game
2. Practice
3. MyPlayer
4. Save
5. Quit to main menu

Its single footer formats the next fixture as
`Away club at Home club. Off field: CPU at normal speed` using native
`49F00`, the authoritative league team pointers and row bytes 2/1 in that
order. Native FONT parsing treats `|` as control markup, so the separator
is a period. The footer falls back to the CPU-speed statement when no own
fixture exists in an admitted playing stage. Practice, MyPlayer, Save and
Quit retain their existing native destinations and return rules.

## PROVED: first Play, league processing, quit and side assignment

The fresh Undrafted path executes native `13EE10` and starts at stage 7
with preseason enabled, or stage 8 with it disabled. The proposed stage-1
explanation is refuted for this fresh-creation path. For the seeded retail
49ers career, the earliest own preseason fixture is slot 27, week 1, while
the initial cursor is week 0. Mode 3 ran the native intervening week and
returned, requiring another press. It did not prove a skipped own fixture.

The new action retains the native advance and continues into the first own
fixture after it finishes. The 49ers proof starts at week 0, executes the
real advance, then enters Team Select for that same first own fixture with
one Play press. The fixture remains unplayed; the observed CPU simulations
exclude the career club. For a current-week fixture, native `C79F0` opens
it directly. At a bye, the same action continues after the native advance.
When no own fixture exists at all, the existing notice and native stage
advance remain. The native progress display can still appear while other
league games are processed; it no longer requires a second Play press.

A separate complete-week regression proves the advance simulates and
commits all 15 other pending games after MyPlayer's completed regular-season
game. `C7A20` and `1356D0` observations exactly match those games. The same
press then opens week 1's first own fixture. An initial implementation
that selected a future week directly failed this regression by bypassing
those results; it was discarded.

The quit policy is explicit: a game abandoned before native completion
stays unplayed and can be retried. Retail pause/quit confirmation sets the
end signal to zero. However, both `C5D60` and `C74E0` originally admitted
any signal other than zero/one, including running signal 3. For an admitted
inline career only, the four result-getter call sites now admit exactly
completed signal 2; other signals become zero at those consumers. The
actual engine global is not changed. Ordinary Franchise returns its exact
retail signal.

The proof executes native match roster/stat constructors, real pause row
12, quit confirmation row 2, teardown and Apartment return. The entire
fixture grid is unchanged; Play reopens the same slot. Additional home and
away cases execute `C5D60` for signals 0, 1 and 3 without fixture/point
writes and reach `C74E0`'s no-result branch. The latter observation stops
before native menu pop, using an explicit code boundary hook because an
already cached Unicorn block can run past its `until` address. Existing
played/completion tests retain real native result and stat writers for
signal 2, once-only awards and Auto Save ordering.

`C79F0` now receives the career's stored controller port, rather than a
hardcoded zero. Its native `C73B0` imports row byte 1 as home (`77AE0`),
byte 2 as away (`77B20`), then `77200` assigns that port to its club.
Tests remove the older fixture's side-get/set service seams and execute
both native helpers. Club 2 defaults away and club 3 defaults home; the
actual imported MyPlayer match record agrees. Team Select remains visible.

## PROVED: marker, receiver icons and play art

The binder already put the selected body's marker value at `body+44` and
kept input on MyPlayer. The missing renderer prerequisite was the side's
raw human flag: `75D40` returns zero if both `E5FC50` and `E5FC90` are zero.
`75D90` also uses those flags to expose receiver icons and art. MyCareer
intentionally clears them to keep teammate/CPU ownership, so its separate
play-call eligibility predicate alone could not enable these visuals.

The existing draw call at `11A8F5` now enters `mode_visuals`. It revalidates
the actual on-field MyPlayer and temporarily supplies its side's `+30`
flag only during unchanged `75D90`, then restores the exact old value.
The native marker and receiver-index functions run; team planners and
controller transfer run outside this scope. Retail replay/presentation
visibility rules are retained.

In a two-actor native fixture on each side, the unchanged renderer submits
no marker and receiver icon sentinel 5 with raw flags zero. The adapter
submits marker 1 under MyPlayer only, and the eligible receiver's native
icon 2. MyPlayer retains port 0; the receiver remains CPU port -1; both
side flags return to zero. Receiver ordering and scene/model inputs are
explicit bounded preconditions. `190940/1907D0` perform actual icon
eligibility; final `FA270` model submission is a declared leaf.

Pre-snap input `120A20` reads a different predicate, team `+24`: offense
modes 1/5 require it when held input contains `6000`, and defense mode 0
requires it for held `2000`. It is also zero in the binder path. The
adapter at caller `1212A5` checks that the supplied input object is exactly
MyPlayer's bound controller, saves its side's `+24`, supplies one around
native `120A20`, then restores the original word. The complete analog and
button decoder `1211E0` remains native. A raw native call and a call with
the teammate's controller both refuse art; MyPlayer's call sets `E60264`
and the renderer reaches native art submission `182480`.

The first attempted hooks were inside Abilities' pinned `120A20` span.
Full composition correctly refused them. Moving the hook to the caller
preserves that entire dependency and avoids changing the Abilities owner.
The native controller/binder and CPU-choice/frame/rule regressions pass.
This proof does not replace a physical passing play or the all-position
normal-speed drive witness matrix.

## PROVED camera boundary; HYPOTHESIS exact witnessed shot

The pre-lineup presentation is phase 7 in `A5620`'s camera table:
`4F0430` contains flags `1B` and descriptor `A88460`. Its callback `A4650`
contains the two retail random eye-height branches, 165 and 800. The end
of `89590`, after play/task work, selects phase 7 for an all-CPU match.
MyCareer's cleared raw side flags therefore send an on-field human player
through that CPU camera decision. An earlier phase-1 hypothesis was
rejected; phase 1 aliases gameplay/play-call preview behavior.

The owned hook at `8970B` sends a present MyPlayer through the same native
human branch `89722`; an absent MyPlayer keeps the original CPU branch
`8973A`. It does not change preceding tasks, raw ownership flags or camera
descriptors. If native logic still selects phase 7, the focus adapter
preserves the original native cinematic/skeleton focus instead of replacing
it with MyPlayer's world position. Phases 9, 11, 14 and 16 retain the
previous MyPlayer focus substitution exactly. No gameplay-camera tuning
value was changed.

The native branch and six focus-call arguments are checked on bounded
instructions, including ordinary-human fallthrough. HYPOTHESIS: these two
presentation mismatches explain Noah's rare high QB walk-up view. Without
his captured frame or a played build, this is not proof of that exact
random shot's final image. Noah must compare that presentation and confirm
that the gameplay camera he liked remains good.

## Allocation and Supersim decision

The owner remains exactly 8192 RX / 4096 RW, with no new reservation or
unreserved cave. Initial RW stays entirely zero. Runtime text, menu and
fixture formatting use the owned RW allocation; RX contains only code,
immutable templates, compact text and the format seal. The generated
runtime reproduces with GNU gcc/binutils and the installed `-Oz` setting.
Direct native-call assembly includes register, flags, memory and x87
clobbers. Native calls remain memory barriers; the compact global reads
are not used as asynchronous hardware polling loops.

The main menu block is 1052 bytes at RW offsets 200..1251, within its
1080-byte subrange. Inline staging is 1280..1407. ASCII text expands to
UTF-16 at 1408..2559. The creation-only 33-row club table overlays
432..2147; its title remains immutable and its footer is retail. Normal
parent reconstruction restores the overwritten menus/text on event 3.
The CAP rollback record, names and free-agent tail word moved to
3312..3467, after the controller-visit array. The dynamic fixture buffer
uses 3468..4095 (314 UTF-16 characters). Persistent footer format and
validation are unchanged; a shared field-index table compacts its encoder
and decoder. Cancellation, save/load and controller-array proofs cover
these reused spans.

`tools/mycareer_mode/mode4_budget.json` records 7544 machine bytes. Minimal
layout content is 8167 bytes plus the existing 17-byte seal, leaving 8;
the budget-union layout uses 8169 plus the seal, leaving 6. Apply receipts
report actual relocated content and spare bytes, rather than the
address-zero template's slightly different compression result.

`measure_mode4.py` appends a concrete, deliberately incomplete
`fastforward_candidate.c` only in a temporary compiler directory. Its
admission/presence/end checks and bounded native-frame loop add 48 machine
bytes. The normal owner refuses 8232/8234 required RX bytes, 40/42 over
budget, before any scene, timestep, animation, pause, interruption, UI or
live-resume implementation. The candidate is neither installed nor
executed. This is a lower bound for that design, not a universal minimum
or a claim that 42 more bytes would finish Supersim. A stop-to-Apartment
lifecycle is also unimplemented, not approximated by terminal simulation.

The existing Supersim reference still has `RUNTIME_READY=False`; native
sim finalization is not a safe live-game resume. Accordingly, the installed
footer while MyPlayer is absent reads exactly:
`CPU plays until MyPlayer's unit is on the field`.
Its actual retail glyph path is tested. The Apartment explicitly states
normal CPU speed. No accelerated play or live skip is advertised.

The refreshed M3 purchase-core measurement uses current Oz sources: 8568
required RX, 376 over, with no UI/remaining M3 surfaces. The Os reference
requires 8643, 451 over. Nine rows would require 1260 menu RW bytes against
the current 1080 subrange. Historical mode-3 receipts are left historical.
Upgrades, calendar/depth UI, trade/release requests, draft/Senior Bowl and
bound Apartment art remain unimplemented and unaccepted.

## Validation

All commands below use standalone `python3 tests/mod_editor/<filename>`.
Qt unit tests use `QT_QPA_PLATFORM=offscreen`. Both gates, the oracle suite
and manifest-aware owner suites receive
`NFL2K5_CAVE_MANIFEST=$PWD/.scratch/mode4-manifest.json`. The completed
runs in this table have no skips. Times are unittest elapsed seconds;
peak RSS is measured per process with `/usr/bin/time`.

| Standalone test | Passed | Seconds | Peak RSS KiB |
| --- | ---: | ---: | ---: |
| `test_nfl2k5_cave_oracle.py` | 28 | 202.065 | 908,996 |
| `test_nfl2k5_franchise_autosave.py` | 7 | 8.587 | 117,752 |
| `test_nfl2k5_franchise_autosave_unicorn.py` | 15 | 7.734 | 389,520 |
| `test_nfl2k5_guardian_manifest.py` | 1 | 167.829 | 239,012 |
| `test_nfl2k5_music_playlist_manifest.py` | 2 | 3.593 | 131,472 |
| `test_nfl2k5_my_career.py` | 13 | 19.943 | 130,360 |
| `test_nfl2k5_my_career_completion.py` | 6 | 26.715 | 330,576 |
| `test_nfl2k5_my_career_control.py` | 2 | 14.000 | 213,364 |
| `test_nfl2k5_my_career_cpu_choice.py` | 1 | 19.215 | 146,572 |
| `test_nfl2k5_my_career_cpu_frame.py` | 1 | 56.682 | 133,716 |
| `test_nfl2k5_my_career_cpu_injury.py` | 1 | 22.795 | 133,640 |
| `test_nfl2k5_my_career_cpu_period.py` | 2 | 35.850 | 169,684 |
| `test_nfl2k5_my_career_cpu_timeout.py` | 1 | 20.025 | 133,744 |
| `test_nfl2k5_my_career_cpu_turnover.py` | 1 | 20.513 | 133,832 |
| `test_nfl2k5_my_career_creation_boundary.py` | 4 | 2.076 | 185,068 |
| `test_nfl2k5_my_career_frontend.py` | 7 | 49.767 | 376,016 |
| `test_nfl2k5_my_career_generic_build.py` | 5 | 15.005 | 173,336 |
| `test_nfl2k5_my_career_inline.py` | 8 | 11.417 | 291,488 |
| `test_nfl2k5_my_career_manifest.py` | 3 | 5.963 | 136,948 |
| `test_nfl2k5_my_career_mode4.py` | 8 | 413.191 | 292,892 |
| `test_nfl2k5_my_career_mode_audit.py` | 6 | 0.061 | 65,760 |
| `test_nfl2k5_my_career_mode_routes.py` | 7 | 2.716 | 229,708 |
| `test_nfl2k5_my_career_panel.py` | 4 | 0.169 | 68,968 |
| `test_nfl2k5_my_career_played.py` | 4 | 45.692 | 222,512 |
| `test_nfl2k5_my_career_season.py` | 1 | 171.787 | 194,804 |
| `test_nfl2k5_my_career_unicorn.py` | 18 | 12.540 | 361,312 |
| `test_nfl2k5_my_career_week.py` | 1 | 349.391 | 170,272 |
| `test_nfl2k5_owner_pairwise_composition.py` | 101 | 599.457 | 193,568 |
| `test_nfl2k5_screen_hooks_manifest.py` | 3 | 3.707 | 129,884 |
| `test_nfl2k5_supersim.py` | 12 | 8.451 | 265,088 |
| `test_xbe_patch_memory_writes.py` | 91 | 794.756 | 341,844 |
| `test_xbe_patch_cave_references.py` | 103 | 917.837 | 527,364 |

The final mode-4 suite has eight tests. The new foreign-boundary assertion
was subsequently strengthened to repin section digests before damaging a
native dependency/hook; its standalone focused rerun passed, 1 test in
6.507 seconds. This proves the owner pin rejects the byte rather than
relying only on a stale section digest. No production source changed after
the successful manifest generation.

Additional Defensive Try manifest validation: its unmodified standalone
suite initially refused the expected stale protected manifest, because
that older file ignores `NFL2K5_CAVE_MANIFEST`. The same three tests passed
in 4.072 seconds, peak 160,836 KiB, using
`NFL2K5_CAVE_MANIFEST=$PWD/.scratch/mode4-manifest.json python3 .scratch/with_manifest.py tests/mod_editor/test_nfl2k5_defensive_try_manifest.py`.
The small harness fully validates the generated manifest against retail
and current source fingerprints, assigns that path to the imported
`oracle.DEFAULT_MANIFEST`, then executes the unchanged test with
`runpy.run_path(..., run_name="__main__")`. It changes no reservation,
source hash, assertion or test file. This is disclosed separately from the
ordinary standalone results.

Other successful commands:

```sh
python3 tools/mycareer_mode/build_runtime.py --check
python3 tools/nfl2k5_franchise_autosave_assemble.py --check
python3 tools/mycareer_mode/measure_mode4.py --output .scratch/mode4-budget-repro.json
python3 tools/mycareer_mode/measure_m3.py --output .scratch/mode4-m3-budget.json
git diff --check
```

The reproduced mode-4 budget JSON equals the committed receipt. The
scratch manifest command was:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir /tmp --json .scratch/mode4-manifest.json
```

It recorded 10,792 reservations from 125 observed XBE writer calls; peak
RSS was 815,836 KiB. Its disposable images were deleted. The protected
manifest is untouched. The first generation attempt refused a guard
covering the separate camera owner's gameplay descriptor; the final pins
cover the intended phase-7 descriptor and camera decision instead.
Full composition also caught the Abilities input-span conflict described
above. These were fixed, not waived.

The disc regression command was:

```sh
python3 tools/mycareer_mode/check_discs.py \
  '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json \
  --receipt .scratch/mode4-discs.json
```

Both sequential builds passed owner status, byte-identical replay and XBE
readback hashes. Two different native-created careers cold-loaded on both
executables, reached their own Apartment, opened MyPlayer and returned.
All four loads passed after both disposable discs had already been deleted.
Peak RSS was 184,136 KiB. Each output was 6,312,800,256 bytes; no disc or
archive pack was loaded whole into RAM. These are reservation layouts with
MyCareer and Auto Save installed; complete all-owner composition is covered
by the gates, not implied by this disc recipe.

Output XBE hashes:

- Minimal with Auto Save:
  `47a19105a1365a393dc4b499c34dfa66d3d524a1113dec246e4c62c424544cc8`.
- Full reservation union:
  `d8a5cfb364489bd41034e7ae64a56e2812163766127da3a1096b0f6d1c59c943`.

The minimal paired recipe has a different relocated address than mode
alone: its receipt reports 8164 content bytes and 11 spare. The full
reservation union reports 8169 and 6. The disk checks began with
108,184,035,328 bytes free and ended with 108,183,130,112. During the
manifest build a recorded low was 101,874,765,824, above the 100 GB decimal
floor. The final audit found 108,181,581,824 bytes free and 3,574,074 scratch bytes. No acceptance image or pack copy remains; all processes measured below 2 GB.


## Noah's witness list and known gaps

1. From Game Modes, create an Undrafted career. Read every club name, move
   to the last club, Back, reopen, confirm a different club and Sign.
   Verify the visible selected club is the one that signs MyPlayer.
2. Read the Apartment title, all five labels and the complete fixture/speed
   footer. Check highlight/navigation, Practice, MyPlayer, Save and Quit,
   including return after a game and a cold save load. Check 4:3 and the
   composed widescreen build for clipping or overlap.
3. With preseason on and the 49ers, press Play once. Allow required league
   processing, then verify the first own matchup and controller side. Also
   test an away fixture, bye, completed-game return and next season.
4. As QB, confirm the indicator follows only MyPlayer, held pre-snap play
   art appears, receiver icons appear, passing works, and handing off
   leaves the back under CPU control. Check both home and away, offense,
   defense, substitutions, injury, special teams and replay transitions.
5. While MyPlayer is absent, read the CPU wait footer and watch a complete
   normal-speed drive return to his unit. Automatic animation-driven snaps
   and the combined full-drive/all-position matrix remain unproved by the
   separate native frame/event tests. No Supersim control should appear.
6. Quit mid-game, read the Apartment, then replay the same unplayed fixture.
   Finish another game and check native stats, exactly one award and Auto
   Save after a manual slot has been established and saving enabled.
7. Compare the rare QB walk-up presentation with retail human framing and
   confirm the gameplay camera remains the previously good view.

These witnesses are required before treating the mode as playable/shippable.
No M2b/M3 acceptance marker or witnessed claim is created by this delivery.

## Integration and commit delivery

The existing generic dispatcher, BuildPlan, preset defaults, allowlist,
closure and capability surface remain wired. `WIRING.md` records the
protected manifest regeneration, accurate product text and the older
manifest-test path-selection issue. Every protected file, other GUI file
and release-tag test matches the base. The owner/request union was already
present in both gates and the manifest builder; no reservation row changed.

Delivery uses an explicit-path commit on `astra/r64-mycareer-mode-4`, with
only the 17 code, fixture, test, tool, budget, report and wiring paths.
`ASTRA_BRIEF.md` and `.scratch/` are excluded. Git staging succeeded, so the
read-only-metadata bundle fallback was not needed. The commit identifier
is in this branch's history and the final handoff. Nothing was pushed.
