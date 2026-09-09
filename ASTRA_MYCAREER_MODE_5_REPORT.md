# MyCareer mode 5

EXPERIMENTAL / UNWITNESSED. These changes have not been played by Noah.
The mode-4 club selection, signing, player marker, play art and receiver
icons are witnessed only as described in ASTRA_BRIEF.md. All new claims below
are bounded instruction, resource, serialization or static ownership proofs.
No console boot, GUI, audio or network was used.

## Built

The four owned lists now use the retail navigation renderer: MyCareer entry,
Choose team/Sign, the scrolling 32-club picker, and Apartment. The owned text
pass supplies only the chosen club on the signing screen and the fixture/CPU
explanation in the Apartment. It does not repeat any title or menu row.
Selected native rows are yellow, with the native scene opacity retained and
no L/R decoration. The color change is restricted to the owned manager and
an owned screen handler; ordinary native menus keep their colors.

Signing puts the created record at depth 1 of its position. Players ranked
above its old spot move down once, including the former starter to depth 2;
the remaining order stays intact. Both native rank/side fields are updated,
including paired positions, and the existing depth-lock bits are set.
Apartment has a **Start MyPlayer** action between MyPlayer and Save. Signing,
that action, Practice and Play next game invoke the same bounded insertion.
Repeated restoration is unchanged. It uses the existing validated active
club and created-record identity, not a player name or a replacement record.

Free Practice starts MyPlayer without a manual substitution. It uses his
club on the side appropriate to his position, with the next club as the
opponent, instead of copying his record onto both sides. Native practice
settings, navigation, lineup construction and controller binding remain in
use. The source record and the actual match copy keep their distinct roles.

Two missed native CPU checks now use the existing `mode_human(team)`
predicate. A present MyPlayer QB retains human play calling between plays
and when his offense takes over. The other ten players and the other unit
keep their CPU control. The off-field floating notice is removed from live
play, including substitutions and special-team waits. The Apartment retains
`Off field: CPU plays`; no speculative wait-duration timer or new prompt
interrupts a live play.

Fable art remains unbound for the precise resource-lifetime blocker below.

## PROVED: duplicate rows and selection

The old picker invoked native event-7 drawing through `F3E90`, then mode 4's
owned pass drew the same title and rows again. Its `navigation` descriptor
was valid. The Apartment's old layout-name field instead pointed at the CPU
explanation string, which is not a LAYT name; its owned pass was its only
navigation text. All four owned list descriptors now name retail
`navigation` at `E7F928` and retain the standard bindings.

The native path is `F3CD0 -> F37E0` for resource setup,
`14FF80 -> 2C8810` for row construction/binding, then
`F3E90 -> F2F70 -> 143DE0 -> 143A00` for LAYT traversal.
`nav_menu_a` contains `nav_menu_list_a` MRKS under the `navigation_text`
instance. `143450` matches the native binding table at `AD0018` and calls
`2C8730` for the row text. The MRKS window contains seven rows and its own
shadow/foreground submissions; those native style layers are not a second
owned list. The independent owned glyph capture is empty for the club picker.

The new fixture runs native LAYT relocation, lookup admission, binding,
traversal, MRKS callback matching, row formatting and scrolling against four
pinned resources, totaling less than 19 KiB decoded. Scene geometry,
transforms and final MRKS drawing are explicit fixture leaves. This proves
which renderer submits the rows and their tint, not final rendered pixels.
The separate existing FONT fixture still executes native glyph walking for
the two supplemental strings. The mode-4 fixture had substituted both the
layout loader and row-binding step; its earlier universal "native draws no
text" conclusion did not cover the resources Noah's game loaded.

`2C8790` retains the native `30AB0` text copy, then tints only the selected
owned row's text context. Tests cover every club through the native scrolling
window and A/Back paths, all four owned lists, and a native-handler negative
control. Opaque selected text is `FFFFFF00`; scene alpha and other row colors
remain native. The old owned `6BC30` decoration argument is no longer used
for menu selection, so no extra L/R glyphs are submitted.

## PROVED: play calling, starter and practice causes

`mode_human` deliberately derives human eligibility from the bounded binder,
unique on-field identity, team pointer, normal scrimmage phase and position.
It does not turn the whole team into a human-controlled team. Consequently,
the native raw team-human words at `E5FC50/E5FC90` remain zero. Mode 4 had
covered several play-call consumers but missed two checks:

| Native site | Role | Original bytes |
| --- | --- | --- |
| `189D9B` in `189D10` | CPU coach hurry-up strategy admission | `8b463085c0` |
| `A30FE` in `A2D40` | Late CPU time-pressure/hurry-up branch | `8b463085c0` |

Both now call the existing register/flags-preserving `human_esi` adapter.
The whole containing routines and hook bytes are pinned. For a present QB,
the coach routine returns before CPU strategy and before `189270` can force
a hurry-up play. The later branch also exits through the human path.
Reverting just either MOV/TEST in an instruction fixture, with the same QB
still bound, reaches the old CPU branch. This explains how CPU coach/time
conditions could take over after a play despite successful initial play
calling. It does not establish which particular coach branch Noah hit in
his recorded run.

The full `A11F0` lineup/play-call initialization runs before each assertion;
no test substitutes a play chooser or makes `mode_human` return a constant.
Tests cover repeated boundaries on two clubs, including the Raiders, and
quarter/time inputs. The native turnover-on-downs fixture runs snap, clock,
dead-ball rules, possession change and the next lineup: an absent QB leaves
CPU calls active, while the newly starting QB returns to human play calling.
The punt variant uses the native special-team lineup and punter, supplied
snap/catch animation events and a returner's possession event, then runs the
same clock, dead-ball rules, possession change and next drive. Its starting
QB again gets human calls. The snapper is a declared native punt-unit actor;
physical long-snap selection, punt flight and the catch animation are not
proved. Only missing HUD scene-clock setters and the punt camera backing word
are additional presentation seams.
The native manual hurry-up entry is not patched; real button behavior remains
on the witness list.

Mode 4's generic creation never requested its older one-time starter flag.
Native signing/depth sorting therefore left the newly created player behind
existing players. Mode 5 explicitly inserts that record and provides a
restoration action. All 17 position codes pass initial insertion, restoration,
rank/side lock and unchanged replay checks. Existing CPU-only regressions now
explicitly declare their intended benched match-record rank before the native
depth constructor; they no longer accidentally depend on the creation bug.

The previous same-club practice setup also copied the primary record into
both match rosters. The common copy hook recorded the last copy, which could
be the opposite side from the practice offense. Distinct teams remove that
ambiguity. Native practice lineup and binding tests cover QB, WR, CB and DE,
with human play-call eligibility and only MyPlayer's controller assigned.
The native command walker advances by `0x24`: its owned entry command now
reserves 36 bytes plus a zero terminator, rather than relying on adjacent RW
bytes being zero. The fixed menu arena remains within its original bounds.

## Budget, refusals and composition

No new owner or allocation was added. Machine code is 7,582 bytes. With text
and menu templates, the minimal layout uses 8,166 bytes and the full budget
union uses 8,165, leaving respectively 9 and 10 bytes before the 17-byte seal
in the existing 8,192-byte RX allocation. RW remains 4,096 bytes; persistent
fields, inline footer, CAP rollback and bounded binder scratch retain their
format. The expanded menu uses 1,072 of its 1,080 bytes. Mutable state stays
in owned RW; text/templates stay immutable. Generated assembly is reproducible.

`status`/`apply` remain exact, refusing mixed, damaged or older mode templates
before mutation and replaying a matching install unchanged. Section digests
are repinned by the existing helpers. All owners retain their original union,
and Auto Save remains an optional composed owner with the same completion ABI.

## Validation

Final commands, counts, timings and peak resident memory are recorded in
`tools/mycareer_mode/mode5_validation.json`. Every test command is standalone
`python3 tests/mod_editor/test_*.py`; the Qt panel test uses
`QT_QPA_PLATFORM=offscreen`. No process loads a whole disc or archive pack.
The navigation fixture uses exact bounded resource reads and precise evidence
skips. All 34 standalone suites passed, totaling 476 tests, including both
XBE gates (91 memory-write tests and 103 cave-reference tests), the complete
101-pair suite, mode 2/3/4 regressions, Auto Save composition and the new mode-5
and three turnover/punt boundary tests. Peak process RSS was 908,476 KiB,
below the 2 GB limit. The final pairwise run started after the last runtime
template edit. Test timings are unittest's reported elapsed seconds.

The normal runtime and Auto Save generators passed `--check`. The mode-4
fast-forward and M3 purchase-core capacity measurements were reproduced in
scratch; neither candidate is installed, executed or accepted as a feature.

A full disposable disc build was refused before copying: free space was
106,004,299,776 bytes and the source disc is 6,300,499,968 bytes. Subtracting
just that copy leaves 99,703,799,808 bytes, below Noah's 100 GB floor before
any XBE growth. No acceptance disc or archive copy was created.

For the XBE gates, `tools/mycareer_mode/refresh_gate_manifest.py` makes a
conservative scratch projection with the oracle Recorder observing actual
MyCareer writes. It verifies every unchanged parent source fingerprint and
checks each changed mode source against the parent manifest's pinned base
revision, `77d1c49f682e380b75f1a7290a806a47845608a9`.
It retains the parent's reservations and allocator layout and adds the newly
observed retail hook spans. Its metadata explicitly distinguishes this from
a new disc build; parent disc hashes are historical. The protected release
manifest is unchanged and still needs Claude's full release regeneration
when a disposable copy can retain the required free space.

## Art blocker and HYPOTHESIS limits

The pinned resource hierarchy is shared: `navigation` (outer 3, chunk 75),
`nav_menu_a` (outer 8, chunk 21), and `title_bar_wide` (outer 3, chunk 71).
The Apartment now uses that existing hierarchy. The Fable image recipe and
owned bitmap assets do not supply a proved Apartment-only SCNE/TXTR lookup,
registration, loading and unloading path. No such family was established in
the bounded LAYT inventory. Binding needs private resource names and a proved
enter/back/load/quit lifetime, followed by checks against other native menus.
There are no archive or shared Crib texture edits in this change.

Final scene animation, pixel placement, complete physical plays, every live
punt/return and coach situation, manual hurry-up button behavior, and extended
controller sessions remain HYPOTHESIS until played. The instruction fixtures
do not constitute game footage. Native position eligibility remains the
existing mode policy: ordinary skill/defensive roles get unit play calling;
special-team calls and lineman roles retain the prior CPU policy. Supersim,
draft entry, attribute purchases and M3 remain unavailable as previously
reported. Nothing in this session claims those earlier gaps are closed.

## Noah's witness list

1. Create a QB, including a high-rated Raiders QB. Check entry, Sign, all 32
   clubs and Apartment: one list, selected text yellow, no L/R decorations,
   scrolling through the last club, and correct signing destination.
2. Check depth 1 immediately after signing and the displaced starter at 2.
   Change the chart, choose Start MyPlayer, and verify restoration and repeated
   unchanged use. Check a paired position such as WR or CB too.
3. Enter Free Practice as QB and a defensive position. Play immediately
   without substitution, call plays, use Back/pause/quit, and return to the
   Apartment with the correct player and team.
4. Play a drive with completed/incomplete passes, runs and scrambles. Call
   every QB snap; try two-minute/end-game situations. Allow CPU defense, then
   check calling after a turnover, punt return, kickoff and new drive.
   Choose hurry-up manually and confirm it happens only when requested.
5. Check fourth down, bench, injury and substitutions: no floating notice,
   no control transferred to a substitute, CPU teammates still active, and
   normal-speed off-field play. Recheck marker, receiver icons and play art.
6. Manually save/load, quit an unfinished game, finish a game with Auto Save
   on, cold-load the career, restore the starter and play again. Confirm the
   fixture/result, player identity and controller survive each return.
7. Check ordinary Franchise, Game Modes, Team Select and the Crib after
   leaving MyCareer. The shared presentation must remain intact. Apartment
   art is not installed and is not an acceptance claim.

## Delivery

Only feature sources, their development tools/tests and this report/WIRING
are delivery paths. ASTRA_BRIEF.md and all scratch evidence are excluded.
The commit on `astra/r64-mycareer-mode-5` uses explicit delivery paths from
the base revision above. Its delivery receipt records the resulting commit
and exact paths. No push.
