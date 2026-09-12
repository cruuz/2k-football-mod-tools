# Beta 68 T3: Berman, Supersim, PAT and read option

Branch `astra/b68-t3-game`, supplied stack base
`c8783a64406ce6b062a7b287173ecbe778f43df2`. All in-game outcomes for this
revision are **UNWITNESSED**. PROVED below means pinned instructions or bounded
native execution, never an emulator, display, audio device or played game.

## Supersim: an owner write explains Off after the game

andrethealchemist: "Super sim fast forwards initially, but stops working
completely after first possession or if you press 'b' during the fast forwarding
process." Also: "After the game, supersim defaults to 'off' in apartment settings."

**PROVED:** `tools/mycareer_mode/runtime.c` contained two writes of **1** to the
persistent Supersim word at base RW `+2696`: one in `mode_skip_ready` on B and
one in `mode_ff_ready` on B or controller disconnect. The frame hook is
`747CC -> mode_ff_frame`; the presentation hook is `64D27 -> mode_skip_tick`.
The Fast forward cancellation check preceded `mode_unit_present`, so pressing
the B receiver during a human-controlled offensive play also permanently
disabled Fast forward. This is a concrete way to lose it around a possession
without deliberately cancelling an active fast-forward sequence.

The regression on the unchanged stack returned **1 instead of 2** after both
an off-field cancel and a human receiver B. The same test passes after the
change. No setting-menu or save-encoder corruption was needed. `inline_encode`
serializes the already changed word; the Apartment label reads that same word.
The host save mappings in `nfl2k5_my_career_save.py` remain unchanged.

For the single-owner install used by the live series, RX starts at `14DC000`
and base RW at `14F2000`. The two old stores are `14DD521` (owner `+1521`)
and `14DD5AC` (owner `+15AC`): `mov dword ptr [14F2A88], 1`. Neither remains
in the current emitted code. `docs/nfl2k5_b68_t3_instructions.json` records
the baseline/current labels, relocated instruction offsets and content hashes.
Composed recipes relocate this reservation, so use owner offsets for those.

The source now uses a transient cancellation word at RW `+2732`: 1 means wait
for the current live play to end; 2 means wait for the next native state-14
snap. The scheduler and presentation skipper consult this word only for an
absent CPU unit. The saved choice remains 2. A disconnected controller suspends
acceleration without rewriting the preference. Load, creation, explicit Settings
changes and postgame clear the transient word. Settled-player handoff still
uses the native 22-player readiness and pending-snap checks; the eight-update
bound, clock delta, audio worker and CPU snap guards remain in force.

**HYPOTHESIS:** the first-possession report specifically resulted from a receiver
B or transient disconnect. The missing player input trace prevents that exact
attribution. The two wrong writes and their resulting persistent Off value are
PROVED. A silent possession boundary alone is tested separately.

An additional harness ABI issue surfaced while adding the PAT check:
`mode_ff_ready` was a static C helper for which GCC used EAX, while the existing
cadence probe called it with ECX. It is now an exported fastcall entry with an
explicit ECX ABI. Production calls and the native probe use the same ABI.

**PROVED, bounded series:** `possession_probe` retains one native match across
three fourth-down completions: `E5FC20 -> E5FC60 -> E5FC20 -> E5FC60`, with
native play count 1, 2, 3. B mid-drive changes cadence from eight updates to one,
stays at one after release and through the next pre-snap, then returns to eight
at the next CPU snap. Six presented frames run 27 complete native outer updates,
including all 27 football phases on each update. The actual postgame parent
returns to the Apartment; Settings displays Fast forward, RW `+2696` remains
2, and the encoded save's Supersim bits are 8.

The fourth-down situation, completed readiness animations, center possession
and snap events, dead-ball event, camera completion and final game completion
are supplied boundary inputs. `B9B50` supplies the center's omitted possession
event before `9FF80 -> B6F30`; without it the direct re-spot leaves ball enum
`[E602C0]=1`, and `B6F3E` correctly refuses another snap. The camera completion
uses native setter `A5B00`, because `64D3F` correctly suppresses world updates
while its world-hold word is set. No possession, score, save or outer-update
callee is substituted to make the assertion pass. This does not prove the
physical fourth-down plays or natural animation completion.

## PAT: MyCareer vetoed human play calling

andrethealchemist: "After scoring offensively with my player, you're not able
to select an extra point play. The game defaults to extra point FG attempt.
The fast forwarding also disappears after this sequence."

**PROVED:** the MyCareer `mode_human` predicate returned zero unless football
phase `[E602B4]` was 4. PAT is phase 3. It also required MyPlayer's current
actor to be present and the settled-handoff latch to be clear. Consequently the
PAT side was CPU-owned even when MyPlayer had just scored, and remained so
after the kicker replaced him.

The pertinent retail chain is `A11F0` (next play setup), with the installed
human predicate at `A1412`. A zero result falls through `A1419: call 1531F0`
to the CPU choice machinery. `1891B0`, whose human consumer is hooked at
`1891DE`, decides whether native human play calling remains pending; `A143A`
enters `9FBE0` for its play-call presentation. Native menu initialization
`AC480` calls that predicate at `AC60C`; an admitted side activates the menu
word `[B70B2C]` at `AC61F`. The phase-3 branch at `AC765` selects the default
PAT category at `AC774`; it does not change Supersim. The native formation
store/re-spot handler
`A31E0` stores the formation at `A3263`, calls `190730` at `A328A`, then calls
the assignment/lineup reader `1CEAC0` at `A3414`. These are existing consumers,
not new unguarded hooks.

The new predicate recognizes the career's scoring match side during PAT from
the bounded copied player record. It checks range, 84-byte alignment, primary
identity, immutable appearance and position before admitting that side. It
does not require MyPlayer to remain in the special-teams lineup. Fast forward
stays at ordinary speed through this team's PAT and releases the transient
appearance wait; it can rearm for the next absent CPU unit after the phase.
The opponent's PAT retains CPU calling. Non-career games retain the retail
predicate.

The kick-rules owner controls the try spot and re-spots a selected two-point
formation. The accelerated-clock owner controls runoff/re-spot sequencing.
Neither is the phase-3 human-play-call veto. The disappearing Fast forward
has the independently proved B-to-Off write above; no automatic PAT-to-Off
store was found. Attribution of the reporter's exact button sequence remains
HYPOTHESIS.

The new PAT series supplies a completed TD result to `22E050` (with its scorer
actor in context `+19C`), executes the actual score callback `B8400` and try
record application `22E4D0`, then follows `A11F0` into human play calling.
Both native `A31E0` choices are exercised from the same checkpoint: the loaded
ATL Field Goal formation/play and the previously native-chosen scrimmage
formation/play for two points. Supplied successful conversion callbacks
`B8420`/`B8480` select kickoff phase 2; native choice and presented updates
reach readiness 13, and the supplied kicker possession/approach commands
reach state 14 with Fast forward still selected.
With kick rules and accelerated clock installed, the selected kick stays at
the modern 15-yard spot (absolute Z 3200.3999 cm), and the two-point selection
uses the 2-yard spot (4389.1201 cm). Both choices produce eight complete CPU
updates on the following kickoff frame. The mode-only control uses the
retail 2-yard spot for both. See `docs/nfl2k5_b68_t3_series.json`.

The base scene omitted `[B719B8]`, which the play-call update needs at `AE7D1`.
The test supplies an empty loaded scene through native constructor `2F140`;
it does not bypass that instruction. TD result, conversion success, empty
play-call geometry, animation completion and controller menu selection are
declared inputs. A scored touchdown, visible menu navigation, physical kick,
two-point attempt and playable kickoff remain UNWITNESSED.
An additional inspection of that PAT boundary observed phase 3, state 11,
human predicate 1 and native menu-active word `[B70B2C]=1`. The scene fixture
omits controller-to-side import (its native port lookup `771F0` returns 0)
and substitutes generic menu/device services. Therefore this proof establishes
menu activation and native acceptance of both supplied formations, **not cursor
navigation or a mapped controller selecting the two-point play**. Those are
explicit items in andrethealchemist's retest below.

## Berman: a reported trigger, no new stopped instruction reproduced

andrethealchemist, replying to TheWildJeffrey: "For me, this happens when
'scorebug effects (diagnostic only)' is selected. Unselecting that option fixed
the issue for me." This is the community's selected/unselected comparison.
It identifies `scorebug_runtime` as a reported trigger. It does not supply a
stopped instruction, failing resource or heap snapshot.

**PROVED:** the seven-test historical freeze suite passes on this stack. Its
old binding still enters `FCE56 -> 42C00 -> 44DC0 -> 28F40 -> 33660`, repeating
at `3367A` with a supplied pending GPU fence. The installed HUD-scoped binding
returns with that same fence pending. This earlier fix was already installed;
it is not presented as a beta-68 fix for andrethealchemist.

`test_nfl2k5_b68_game_composition.py` explicitly enables `scorebug_runtime` in
ADVANCED, simwin66 and the extended 66.1 BuildPlans and runs the production
XBE passes and actual read-intent preview compiler. All three composed cases
pass native GAMEDATA collection load, HUD setup at `FCE56`, 40 updates at
`FCFA2`, font glyph submission, re-entry and the separate native presentation
check. Fresh simwin66/extended careers also reach kickoff readiness state 13
and the native approach-command state 14 in the 66.1 series harness. The
paired read-option recipes activate on both composed stacks.

The scorebug loader control starts at `6310E` and executes the native opener,
which creates ordinary named context `B33D5C` with `E614B8` naming GAMEDATA.
VFS open/extent success and heap selection are explicit services; the real
reader callbacks allocate, decompress, relocate and register the collection.
The entry/update checks retain native lookup at `449E0`, HUD-local lookup
at `43F50` and material-name search at `FBC70`. Private fonts and textures
must be resident in that named context; the scene's material entries and
FONT descriptors must remain valid. The existing native tests cover missing
resources, allocation refusal and old-end-of-file omission without a spin.

The required scene materials are `hscore_buga` and `zscore_buga`. Each side
looks up four `sb{asset_code}{h|a}{0..3}` TXTR descriptors, falling back to the
neutral `--` identity. The seven private FONT names are `score_bug`,
`dscore_buga`, `score_buga`, `zscore_buga`, `hscore_buga`, `core_bug` and
`ore_bug`; the type is significant because some names also identify SCNE/TXTR
resources. The complete native collection run registers 308 TXTRs and seven
FONTs in 730 callbacks, using 2,435,200 heap bytes. Appended panels are 128x32
P8 native resources; these are loader-returned descriptors, not pixel pointers.

In the recorded simwin66 composition, `FCE56` enters setup at `14BA2C0` and
`FCFA2` enters update at `14BA4A1`. The observed cached-material stores are
`14BA51F` and `14BA5DB`, `mov [ecx+30], edx`, using material pointers from
owner RW `+8/+C`. Both complete with resident resources. These are concrete
places to inspect if the real scene's lifetime differs. **HYPOTHESIS:** a
freed nonzero material with `[A95528]` still equal to the cached scene would
pass the owner's scene/null checks and fault at such a store. The current
fixture retains the resources throughout the transition; it cannot establish
whether the player's loader actually creates that lifetime overlap.

**Not reached by these harnesses:** the player's actual order and lifetime of
asynchronous GAMEDATA/other collection loading, GPU texture release/completion,
the complete Berman movie/audio/world initialization, authentic scene animation
completion, custom imports and restored game-state/save inputs. The resource
fixture substitutes unrelated parent calls at `64710` and animation/device
services; the football series fixture has its own scene boundaries. They are
separate bounded witnesses, not one uninterrupted cold boot through Berman.

**HYPOTHESIS:** a different resource lifetime, malformed resident lookup chain,
stale nonzero scene/material/FONT pointer, resource pressure or asynchronous
device state explains the remaining selected-option freeze. None was observed
as a production failure, so no speculative timeout, missing-font bypass or
native wait suppression was installed. To select an instruction-level cause,
capture the stalled main-thread PC/backtrace, `[B09584]` pending queue,
`[B09578]` collection list and its GAMEDATA node, `[A95528]` HUD scene,
`[A95520]` visibility, selected FONT/material/texture pointers, and football
phase/state `[E602B4]/[E602B8]`. Repeated audio alone cannot supply these values.

**WIRING:** the visible option becomes "Scorebug effects (reported Berman
freeze)" on Build and Gameplay. Its shared help and registry row quote the
reporter's workaround and say to leave it off for normal play. Those protected
files are specified exactly in `WIRING.md`, not edited here. The option remains
EXPERIMENTAL, manually selected and false in every preset. No Berman fix is
claimed.

## Read option

Noah / SOFTDRINKTV, September 8: "read option/rpo is broken currently btw".
The beta-66.1 owner research and v5 identity/control contract are retained.
Native recipe, runtime, decoder, frame, control, screen-hook composition,
final-book pairing and separate-book suites are rerun for beta 68. The new
composition test additionally compares the final recoded/paired MIN table to
the BuildPlan-installed table, then executes both I Jokers recipes through
native GIVE/TAKE and the supplied exchange event on simwin66 and extended
stacks. No read-option production change is made merely because an old report
exists.

**Witness boundary:** successful activation is not a played mesh. The current
human contract is no new input = give; release and re-press Xbox A = keep;
Black = pitch; RPO X/named receiver = pull and pass when ready. Natural snap
arrival, exchange timing, animated cancellation, lateral catch, pass release
and catch, contact and actual mapped controller input remain UNWITNESSED.
The diagnostic's expected I Jokers resource indices are 155 and 157; the
separate authored Gun recipes are 134 and 31. A raw old "READ miss 48" does
not identify the current recipe. The four tests requiring Noah's old private
`bo` diagnostic disc skip precisely because that disc is absent here.

## Questions to include with the Build summary and retests

These questions are for Claude/Noah to relay. No message was sent to Discord.

- **TheWildJeffrey:** "Please paste the failing disc's Build summary and say
  which beta, mode, teams and roster/save you used. Was Scorebug effects
  (diagnostic only) selected? Does an otherwise identical rebuild from the
  original source with only that option off get past Berman, through kickoff
  and through the first scrimmage snap? andrethealchemist says unselecting it
  fixed his freeze."
- **lt9608:** "You said 'it kept freezing, and the new kickoffs and things
  didn't show up'. Please paste the Build summary: was Scorebug effects
  selected, and was Dynamic kickoff selected? The new kickoff requires
  Dynamic kickoff in that build. Does the same recipe with Scorebug effects
  off and Dynamic kickoff selected get past Berman and show the new kickoff?"
  The missing-kickoff half points to Dynamic kickoff not being selected or
  installed; the summary verifies that rather than assuming every preset
  enables it.
- **andrethealchemist:** retest a fresh beta-68 MyCareer build with scorebug
  effects off, and include the full summary, especially kick rules,
  accelerated clock, Dynamic kickoff and MyCareer. Set Supersim to Fast
  forward. Watch two possession changes; cancel midway through a CPU drive
  with B; it should stay at normal speed until the next CPU snap and then
  resume. On your offensive appearance use a B receiver. Score, choose a PAT
  kick, then score again and choose a two-point play. Verify the play-call
  screen, selected play, spot, control, following kickoff and subsequent
  off-field Fast forward. After the game open Apartment Settings, save and
  reload: Fast forward should still be selected. Report any different result
  with the phase and last input, not only that the ticker disappeared.
- **Noah:** "On the current beta, which book, formation and exact read/RPO
  play fails, and is it a human or CPU call? Please include the Build summary
  and controller mapping. Does the diagnostic activate at snap/pend on I
  Jokers Zone Read 155 or RPO 157, and which action fails: automatic give,
  release/re-press A keep, Black pitch, or RPO receiver pass? Does it fail on
  the first snap or only after a turnover/audible/timeout?" Play both field
  directions, repeat snaps and possession changes, then repeat the separately
  authored Gun recipes. A passing bounded suite cannot confirm or deny the
  reported physical/input symptom without that witness.

## Allocation, validation and delivery

No runtime data enters `.text`. The MyCareer RX reservation remains 20,480
bytes; its two RW allocations remain 4,096 bytes each. Only four previously
unused RW bytes at `+2732` are assigned a new purpose. No allocator request,
peer address, section geometry or XBE file size changes. All writes continue
through the existing pattern-checked, idempotent owner installer.
The regenerated machine code is 14,908 bytes; complete RX content is 18,781
bytes, leaving 1,682 bytes after the 17-byte format tag. The 324-byte content
increase fits the existing reservation (`tools/mycareer_mode/m3_budget.json`).

**Claude must regenerate the protected cave manifest after integration.** The
local gate projection retains the parent reservations and observes this
changed MyCareer writer. It is explicitly not a disc build or a regenerated
release manifest. Root free space was 82 GiB at entry, below the required
100 GiB floor, so no large image was copied. Retail inputs remained read-only
and no retail bytes are committed. There was no network, emulator, GUI display
or audio use.

All four XBE gates passed against the final production sources and the local
incremental manifest, without skips:

| Standalone command (`PYTHONPATH=.`) | Output |
| --- | --- |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | `Ran 115 tests in 1511.059s; OK` |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | `Ran 127 tests in 1703.991s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | `Ran 388 tests in 2135.790s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | `Ran 29 tests in 357.243s; OK` |

Each gate used `NFL2K5_CAVE_MANIFEST=.scratch/t3/gate-manifest.json`,
`QT_QPA_PLATFORM=offscreen` and `PYTHONHASHSEED=0`. The runner
`tools/mycareer_mode/validate_m3.py` records the source hashes at launch,
verifies they did not change during each suite, and records peak RSS. The
largest gate process used 925,712 KiB, below its 2 GiB bound.

`python3 tests/mod_editor/test_nfl2k5_b68_game_composition.py` passed all three
tests in 418.482s. `NFL2K5_B68_COMPOSITION_TRACE=.scratch/t3/composition.json`
enables its optional trace; the derived receipt is checked in at
`docs/nfl2k5_b68_t3_composition.json`. The new live series tests passed together
with `Ran 2 tests in 172.207s; OK`:

```sh
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_supersim_live.py \
  NativeSeriesTests.test_cancel_multi_possession_and_postgame_settings \
  NativeSeriesTests.test_pat_kick_two_point_choice_and_following_cpu_kickoff
```

Both generated-code checks passed:

```text
python3 tools/mycareer_mode/build_runtime.py --check
MyCareer mode runtime verified
python3 tools/nfl2k5_my_career_assemble.py --check
MyCareer template verified
```

The final full live-file run passed **34 tests in 2350.150s**, with no skips.
Its original uninterrupted series completed **3 native plays, 422 presented
frames, 3,376 complete outer updates and 23,223 match RNG draws**. Cadence
checks at groups 1/2/4/8 produced the same native-state hash. Admissions cover
all 17 positions; animated CB, injury-replacement QB, kickoff K and punt P
handoffs reach state 13 with the full 40-second play clock. Both native render
passes visit/register all 22 players. The final full-file derived receipts
are in `docs/nfl2k5_b68_t3_series.json`.

Across the final standalone command list, **55 files ran 1,092 tests: 1,087
passed and five skipped**. The 31 career/support files account for 164 tests;
the nine read-option/book files account for 106. The beta-66.1 transition,
presentation and scorebug group passed 45; the historical scorebug freeze v2
control passed seven; the new composition file passed three; kick rules and
accelerated clock passed 34 and 40. The gate counts and full live file are
listed above. The read-option group has four precise skips for Noah's absent
old private `bo` diagnostic disc; the generic MyCareer build has one skip for
the unavailable 100 GiB free-space floor. No gate or new native proof skipped.

`docs/nfl2k5_b68_t3_validation.json` records **every exact standalone command,
its Ran/OK output, skip count, timing, log hash, environment and final source
hashes**, plus peak RSS for the gate and career runs. It also records the
baseline negative control: the three new runtime regressions fail on the
unchanged stack with four failed assertions (two saved words `1 != 2`, and
home/away PAT eligibility `0 != 1`). All pass in the final full-file run.

`WIRING.md`'s Python and JSON code blocks parse and both registry targets exist.
The last pin check before the proof commit applied zero updates. The final
report commit is also immediately preceded by a repin. Large private inputs,
failed development probes and disposable Git metadata are excluded from the
bundle; reports contain derived evidence only.

The worktree's Git metadata is read-only in this session. Delivery therefore
uses the authorized bundle alternative: `.scratch/t3/git` contains explicit-path
commits on `astra/b68-t3-game`; `ASTRA_T3.bundle` carries that branch above
prerequisite `c8783a64406ce6b062a7b287173ecbe778f43df2`. The original Git
metadata was not modified. Code commit: `32e085cf`; native-proof commit:
`7b9f4aef`. A final report/validation commit follows the green gates. Every
commit is preceded by `python3 packaging/repin.py --apply`.

Claude can import the completed bundle into the integration repository with:

```sh
git fetch /home/noah/2k-worktrees/astra-b68-t3/ASTRA_T3.bundle \
  refs/heads/astra/b68-t3-game:refs/remotes/astra-t3/game
git log --oneline c8783a64406ce6b062a7b287173ecbe778f43df2..refs/remotes/astra-t3/game
```

Integrate that range, apply the protected changes in `WIRING.md`, regenerate
the release cave manifest, repin, and run the release gates. No allocation
changed. Berman remains unresolved, read-option's played symptom remains
unreproduced, and every in-game outcome remains UNWITNESSED.
