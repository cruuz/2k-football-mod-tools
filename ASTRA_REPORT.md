# Beta 66.1 H2: Berman / SEGA transition research

Branch: `astra/b661-game`. Source: beta-66.1 stack `1d38df5e`.
Continued from `d1bfbed2`; its owner census and header mapping correction are retained.

## Finding and evidence boundary

TheWildJeffrey reported “freezing right after Berman and repeating audio.”
jrolling2003 reported being “stuck on the sega screen”; lt9608 reported “it kept
freezing, and the new kickoffs and things didn't show up.” These reports do not
identify a Build summary, source-disc identity, game mode, saved settings or
the CPU's stopped instruction. **No reported game hang has been reproduced
yet.** Bounded instruction execution is PROVED; played behavior is UNWITNESSED.

**PROVED harness defect:** the kickoff `NativeMachine` mapped sections but
omitted the mapped XBE header. ADVANCED's acceleration hook `0x75CD5` calls
`0x10A60` in the owned header-logo span. The fixture executed zero bytes there
and raised `UC_ERR_READ_UNMAPPED`. Loading the actual header before native
execution removes this false positive. A fresh ADVANCED frame and a fresh
simwin66 frame both return; the old fixture's cached zero-code translation
must not be reused after changing its mapping. The 23-test dynamic kickoff
suite passes after this correction. No retail/game instructions were changed.

**PROVED SEGA wait class:** `0x74180..0x7424C` is the still-splash resource wait.
`[0x4E9728]` names `segalogo`; its duration is `[0x4E972C] = 2.0` seconds.
`0x74236` calls `0x432C0`, whose `mov ecx,[0xB09584]; test ecx,ecx; sete al`
returns whether the pending resource queue is empty. `0x7423D: je 0x74190`
keeps pumping `0x38F50` until that queue empties. This is a real retail wait,
not evidence that an optional owner caused the reporter's queue to remain
pending. The regression supplies successful and permanently pending I/O at
the pump boundary and requires return or an explicit instruction-budget
failure, respectively. No DVD, kernel, movie decoder or audio device is run.

**PROVED missing selected-play input:** with a valid team and play-call object
but a zero selected PLAY pointer, `0x189640: mov eax,[ecx+8]` returns zero and
`0x894B0: mov eax,[eax+4]` reads an unmapped address. Retail and every composed
preset do this. With the record present, native decoding sets camera state 8.
This check catches a missing record; it does not establish that a reporter's
resource loader lost that record. The camera timer/control side effects use
the presentation harness's declared leaves.

**PROVED readiness wait class:** the native `0x188228` call to `0x1FF940`
returns false while the kicker's ready animation is missing. In the tested
descriptor (`0x50F1E4`), `0x1FF959: mov esi,[eax+0xD4]` reads that record;
`0x1FF95F: test esi,esi` leaves readiness false when it is zero. Team readiness
therefore keeps `0x158CA6: je 0x158CD5` from advancing state 12. Three bounded
calls stay at 12. Supplying the animation completion input lets native code
write 13 at `0x158CC1`, then the approach call `0xB6F30` reaches 14. This is
proved for retail and every selected preset. No test sets the team-ready bit
or advances the global state from Python after construction.

The former retail/ADVANCED lineup test also had held controller axes and no
controller callback. On its second frame it called zero through
`0x2FC216: call [ecx+0xC]`. Neutral input removes that fixture fault, but its
three-key synthetic clips still do not prove retail animation completion.
The revised test names the animation input explicitly. The full frame test
is retained for all three dynamic-kickoff builds, where the native lineup
completion and installed hold policy do reach 13, then 14. Its
`complete_lineup` input supplies task `+0x38=3` / `+0x3C=1`, then runs the
native completion callback and Start opcode. It does not simulate the full
pregame animation library. The active-career series fixture below performs
its own native lineup construction without that completion input.

## Builds and scope

`tests/nfl2k5_b661_transition.py` starts with `mod_build.apply_preset` and the
BuildPlan options. It obtains the initial and final XBE-pass argument
expressions from `mod_build._build`, runs the production `_apply_all` writers,
and preserves the intermediate pools, depth-chart rows, season, scorebar and
final helmet passes in memory. The Build tab's `_preview_play_intents`
compiles the actual two stock seed books from the private source disc.
This is an executable composition and bounded resource fixture, **not a
completed disc-build receipt**: archive remapping, imported assets and final
PLAY/ROST relocation remain explicit boundaries.

The exact simwin66 reference was recovered read-only from
`/tmp/claude-1000/-home-noah/a0e23b53-6c52-4d9b-9878-b195950f3ca1/scratchpad/b66/ship/simwin66.py`,
corroborated by `BETA66_SHIP_2026-09-10.md` at 00:33 in Noah's handoff archive.
It enables accelerated clock On/20, MyCareer, paired offense/defense books,
read option (two authored seed recipes), QB spy, deep zone facing/bail,
weekly prep and its two suboptions, abilities, 7-on-7, camera v6, and Matte.
It leaves momentum, playlist, screen hooks and dynamic scorebug OFF.

The extended configuration adds those owners, guardian overlay (replacing
the mutually exclusive helmet-C trial), 16 reserves / two extra created teams,
practice-squad screen, music menu policy/unlock/UserList, defensive try,
zone cap, stadiums, coverage slider, scramble tuning, chop-block and Crib cut.
A second extended configuration removes MyCareer. User-supplied audio,
textures, roster edits, ESPN scenarios and incompatible flight variants
cannot literally all be selected together; they are not silently invented.

**PROVED exclusions:** `franchise_2026_rules=True` is refused by
`nfl2k5_franchise_2026.require_runtime_ready()` (`RUNTIME_READY=False`);
its allocated rule kernel has no retail hook or native ledger transport.
`senior_bowl=True` is also refused by `_validate_r62_options` before building.
Neither can be a live owner on a supported beta-66 Build-tab disc. These
refusals are regression-tested, rather than bypassed to fabricate an
“everything on” disc.

No disc is copied. `/` had only 89 GiB free at entry, already below the
handoff's 100 GiB reserve. Private retail inputs are read-only and remain
outside Git. Scratch holds derived logs and temporary Git metadata; no retail
image is written there.

The final receipt records each composed XBE hash, BuildPlan, executable pass
order and every allocated owner address/size in `owned_space`. These are the
exact owned code space locations for these builds, rather than guessed fixed
destinations. The composition fixture does not publish a disc or claim to
replace the builder's final archive/intent read-back gates.

## Owner census: pregame through kickoff / first snap

This is the current beta-63-to-66 owner surface, including earlier owners
still installed by beta 66. “Could” below describes a required bad state,
not a reproduced defect. Native runtime entry VAs are exact; allocator
destinations depend on the selected union and are derived from that build.

| Owner | Exact hook / read VAs | Loop, wait or null condition and scope |
|---|---|---|
| Dynamic kickoff | `222CA0` launch, `222E67` aim, `A06E0` ground, `B78C9` touch, `B7BB0` dead, `1CD5D0` planner, `218010` motion, `2CC4F0` position, `B65CC` spot, `1C9399` reset, `183F60` lineup, `B6760` eligibility, `2CC570` root motion, `2FAFF0` blocking, `1802BB` diagram, `1D8940` separation, `1FF940` readiness, `1DF430` head, `23CE70` block tick, `A7930` commentary; legacy cave `2890F0`, state `A69969` | Native readiness `1881E0 -> 1FF940`, then `158C90` advances global `E602B8` from 12 to 13. A free kicker/returner that never completes its setup prevents readiness. Held coverage/setup slots return ready only after individual `+3E4=13` in state 12, or global state 13/14, phase 2, formation type 8 and no contact flag. Null possession/formation is explicitly rejected. Missing contact after launch would hold movement, but is later than the reported intro boundary. Onside/safety retain retail. |
| Broadcast camera v6 | `5FC74` final-eye clamp, `A55EB` entry selector, `A54C3` spectator choice; `16D1D4`, `16E7B1`, `16E864` settings loads; table `4F03F8`, option `E5FFF0`, state `B616C0`; native lookup `A572D..A5741`, selection tail `896EA`, play-type decode `894A0 -> 189640` | Row 7/state 7 is camera setup, distinct from gameplay state 13. Row 7/state 8 shares the kickoff descriptor after selection. The clamp is finite; it does not wait on readiness. Calling native play decode before the possession/selected-play chain exists could dereference null, including retail. Installed selection must stay within the eight rows. Remaining geometry hooks `A4A2D`, `A4C0C`, `A4B1A`, `A4D1F`; menu hooks `2C66A0`, `2C66D5`, `2C6B00`, `2C6B40`. |
| Accelerated clock | `B86E0` huddle completion, `B6EB0` clock stop, `B6DC0` period reset, `A24B0` no-huddle | Straight-line guards; no spin. Runoff requires state 12 and phase 3/4, positive period, valid clocks and finite bounded seconds. Phase 2 kickoff exits. A never-cleared latch suppresses runoff, not native progression. Native displaced clock functions still require their retail clock objects. |
| Momentum | `1CD5D7` dispatch, `1D9D62` first contact, `1DA39F` later contact; reads curve `50A588`, floor `513E38` / `237D20` | Wraps the same planner whose entry has the kickoff hook. The slot search is bounded to 32 records; overflow falls back. Saved ESI/EDI, EBP frame and x87 state must balance when the full native dispatcher returns. A broken actor state/steering chain could fault; a native task that never returns would hold this wrapper. No unbounded owner retry. |
| Music playlist | `6E4E0` screen event; `F63CA` player init, `F64CD` profile, `F6510` mode; `2801A0` / `280450` enqueue, `2806B2` frame, `28016D` callback, `27F040` / `27FF15` advance, `27FEC0` suspend, `27F6B0` pause, `27F6F0` resume, `27FF90` preview, `2804C0` context; `325E22`, `D90F0`, `D9350` draft/halftime | Bag fill/shuffle is capped at 100. Null/-1 bank descriptors, invalid range/counts, paused/active/preview/loading states return. A missing completion leaves that stream active, without an owner busy-wait. Device/stream internals and resource-manager cycles are outside the playlist's scalar fixture. Global registry lookup is at `449E0`; load pumping is separate. |
| Music collections / jukebox | Table `AC9C80`, menu bank `AC9ECC`, UserList `AC9ED4`; accessors `27F410..27F5D8`, `27F95B..27FD67`, `27FF24..280186`; Crib loop `32A159`, back-edge `32A24F` | Count 18..20 and table displacements are patched together when a user library exists. A corrupt count/pointer can read a nonexistent row; no library is present in the simwin66 reference. The Crib list repair bounds labels at `AE621C` (4 disc / 13 HDD rows), unrelated to kickoff readiness. All accessor instruction VAs are explicitly enumerated in `nfl2k5_music_collections.SITES`; native relocation/accessor tests cover extra rows. |
| Runtime scorebug | `FCE56` setup, `FCFA2` update; scene `A95528`, visibility `A95520`; loader call `6310E`, named collection `E614B8` (GAMEDATA); lookups `449E0`, `43F50`, `FBC70` | Owner skips null/stale scenes, missing material/font/texture and invalid clock/context. Setup clears 128 RW bytes; loops are fixed two sides / bounded font entries. Native registry traversal could hang if a collection list is corrupt. Private lookups are scoped to resident GAMEDATA, not a type-blind global collection. Full art loading is not proved by an XBE-only frame. |
| Screen hooks | `23ECD2` blocker, `19C7E9` QB | Screen-only grammar; finite chain walk, QB lookahead slots through 5. Block wait is permitted only in state 14 with play timer below 0.8 seconds; kickoff grammar fails classification. If the native play timer never advances, that conditional hold can persist across frames, not spin inside one call. Incoming actor/task pointers are the native ABI contract. |
| Screen timing A/B/C/D | Loaded PLAY assignment reader `1A8C00`; resource node pool and per-assignment low-nibble length, no new XBE hook | D changes qualifying finite line holds 0.5 to 0.8 seconds, QB drop -10 to -7 yards, and a default pass timer to 0.6 seconds. A stopped native timer can retain a hold across frames. A missing/zero-length chain is refused by the compiler. PLAY bases are chosen by the loader, so resource-relative receipt offsets are exact; a fixed absolute RAM address would be misleading. Kickoff assignments are outside named-screen grammar. |
| Playbook pair | `62BE0` begin, `630C8` queue, `64710` bind, `61950` cleanup, `166617` load mode, `F71E0` VIP | Main extra-book load occurs before gameplay scene initialization. `pair_bind` rejects missing original/donor or failed allocation and leaves retail root; it does not wait for a donor. Merge validates maxima 50 formations / 270 plays / 26 categories and bounded script nodes. A queued archive request that never completes can strand the surrounding retail loader before bind. Published paired roots are revoked before free. Default Same as offense does not allocate. |
| Read option | `1AF009` tick, `21516A` schedule, `646A1` HUD, `19C849` pass init, `B6FBD` snap, `1AD9C3` reset, `313520` exchange | Activates only on an authored, matched PLAY identity. Paired-root resolver is bounded to two sides. Missing pointers/unknown root or expired task fail to native action. A stale nonzero native actor pointer is not generally made safe by a null check. The kickoff grammar is not a read recipe. |
| QB spy | `B6FB3` snap, `1A5790` / `1A5090` zone, `1B8570` / `18AEFC` reset; `2FDF30`, `2FE130`, `2EFDB0` rush; `1A4830`, `1A4DA0`, `1A4D70`, `1A4DD0` man | 22-record identity search is bounded; full table falls back. Requires state 14, defense, CPU steering, live ball owner QB and authored intent/explicit command. Missing state/task/clock/ball pointers exit; kickoff context `+1C4` exits. Native fallback still requires valid receiver/blocker task fields. |
| Guardian overlay | `8F02E` bind, `8FB45` shine, `C16CD` roster clone | Render-time shell B only; rechecks LOD, scene/material count, native context membership and current texture descriptor. Null scene/material/record/resource exits. A stale nonzero scene/name pointer or a corrupt global lookup chain could fault/hang in a native helper. No owner loop or cached persistent texture pointer. |
| Abilities | `17B010` attribute, `75CC8` speed, `15647D` decode, `18EC6D` dispatch, `1CD550` initialize, `2D43F0` generate, `2D46D0` AI-ready, `2D4740` consume | Stored-flag popcount is finite; carrier, controller and state checks gate action policy. Zero/-1 records return no ability. Attribute hooks can run during scene setup and must not be bypassed by the old frame fixture's attribute leaf when claiming their execution. Dedicated native tests execute these hooks. No owner readiness retry loop. |
| Deep zone | `1A4170` planner, `1A66D5` init, `2FCADD` tick; zone records `BE4B60`, count `BE4D40`, QB `BE4F8C` | Eligibility requires a valid zone index below a count at most 11, so the later decrementing deep-record loop cannot start at zero. Eleven RW records; only active defender/task/assignment identities persist. Null defense/state/task/context/QB paths exit. Not a kickoff assignment. |
| Weekly prep | `134040` before played game; `C7B47` before sim; `2AB701` DB group, `2AC483` gate, `2AB9A2` / `2ABF12` seed, `2483F7` / `2AC53F` remember | Runs before loading the played match, not a new after-Berman tick. Guards franchise mode, prep on, 32 teams, stages 7..9, week<22, slot<17 and two valid team IDs. Roster validation is bounded to at most 65; null player/team exits. Native prep internals still depend on intact roster/schedule resources. |
| Franchise 2026 rule kernel | **No installed retail hook.** Audited future native adapters: `C5280`, `27DBC0`, `2D09C1`, `2D0F3F`, `2D0780`, `247D10`, `247E20` | Build preflight refuses enforcement. These are pinned research targets, not active calls into the dormant kernel. Distinct from the real 2026 season/calendar preset writers. |
| Position pools / SPECIAL rows | `510208` enum->kind, `5101F0` kind->enum, `4F5930` kind lists, `51029C` packages, `521C68` targets, `521C20` maxima; `242B07` row lookup -> cave `2BA840`, `C4138` chain index, `17AA34` penalty; `243D50` tab init | Data readers consume recoded PLAY personnel and reclassified ROST players. Mixing a pooled XBE with a retail/custom saved roster can leave a needed position empty, leading to a missing actor or native lineup wait. This must be tested with the user's save; an executable-only fixture cannot establish data compatibility. Menu selectors `345560`, `345590`, `555AE0`; neither menu loops nor labels are pregame CPU wait hooks. |
| MyCareer (only when enabled) | `74879` HUD, `747CC` outer-frame scheduler, `3E94D` audio, `64D27` skip tick; `8970B` camera pick; `A5490` / `A5947` camera focus; snap gates `2D37E0`, `2ED020`; binder `156246`, `C3C60`, `156640`, `156870`, `1A7970`, `1A77A0`, `1A85E0`, `1A70E0`; `6E390` screen dispatch | HUD exits outside camera states 8..19, so state 7 is excluded. It requires running game, active inline career, matched bounded roster copy and stat/font pointers; fixed format/name bounds fit local storage. Fast forward runs at most eight updates, and settled-player traversal caps at 128. A pending appearance holds CPU snaps until 22 native players are ready with no queued snap event; missing readiness could persist across frames. A non-MyCareer game must fail these gates. Early screen/audio hooks still execute their inactive path when installed. |
| Larger roster / extra created teams | `C2180` disc roster load, `C2040` save load, `C1F90` save, `C0FA0` team export, `C3A90` remove; capacity `C1F2D`, `C1F3C`, `C1EB3`; created-team predicate `319370` | Requires the matching migrated ROST arena (0x92000 bytes) and version-2 team metadata. Loading a retail resource directly into a fixture with these hooks is not a valid full-build input. A missing team reaches `77AE6: mov ecx,[ecx+0x110]`. Native MyCareer creation separately refuses the migrated metadata; see below. |
| 7-on-7 | Practice type `E601D4`, dispatch table `E3434`, book-loader choice `62D15` / `62D39`, owned code `1AC170..1AC25F` | Requires practice type 4; regular kickoff is outside its mode gate. An absent PRACTICE book would affect the surrounding native resource loader. The earlier overflow into live code `1AC260` is already repaired in this branch and is not an installed beta-66 defect. |

## Boot-path interpretation

The still-logo wait, loader queue and the first title-screen path are distinct
from gameplay state 7. The native title input `F5B57` accepts Start, `F5B72`
pushes `515660` through `6E390`, and `F5B7C` invokes music mode `F6510`.
Global screen dispatch (MyCareer `6E390`, playlist `6E4E0`), music initialization
(`F63CA`, `F64CD`, `F6510`, frame/callback routes), camera settings-load hooks,
and primary-roster loaders/attributes are the relevant early surfaces.
Gameplay-only clock, momentum, dynamic kickoff, deep zone, screen-block,
read-option and spy policies require actors/play state. Guardian and scorebug
require their render scenes. Weekly prep requires an active franchise game.
The position/season data can affect loading, but do not replace the SEGA
queue predicate. No statically observed cave-reference violation is assumed
equivalent to proving all computed pointers safe.

The boot census also includes the following data and early calls:

| Installed surface | Exact address / condition |
|---|---|
| XBE logo and allocator metadata | Header fields `10108` (header size), `10170` / `10174` (logo address/length), section table `10370`; original logo/owned code span `10A10..10CC2`. The repaired logo is separate from owned instructions. A loader unable to use the added section/relocated logo remains a hardware/BIOS hypothesis, before the game can pump its SEGA queue. Native CPU mapping cannot prove kernel loading. |
| Menu music policy, unlock and UserList | `AC9ECC`, unlock fields `AC9C94 + collection*0x20`, `AC9ED4`; collection table/accessors are listed above and in the receipt. These can be read by menu-music startup; a count/table mismatch can request a missing collection. Imported audio and actual stream completion are outside the scalar bank fixture. |
| Title Start and installed menu hooks | `F5B57..F5B81` executes the screen push at `F5B72 -> 6E390` and music mode at `F5B7C -> F6510`. Both extended builds reach `F5B81`, with their real MyCareer/playlist code installed. A missing music bank queues nothing and returns; present banks queue one item. Profile I/O, controller assignment and screen rendering are declared services. This starts after the title has accepted Start; it is not a full cold boot. |
| Camera saved setting / initial objects | Settings readers `16D1D4`, `16E7B1`, `16E864`; object construction `A55A0 -> 5F710`; camera option `E5FFF0`. These must see a valid row index before native row lookup. The finite v6 clamp itself has no wait. |
| Primary roster and attributes | `C0500` relative fixup, `C2180` loader (larger-arena owner when selected), `17B010` ability-aware attribute reader; the position tables listed above. Missing archive completion or mismatched ROST/XBE layouts remain possible inputs to a loader wait. The simple frame's attribute leaf does not prove native attribute execution; the abilities native suite does. |
| Calendar / season data | `1C1880`, `1C19F0`, `1C1940` date helpers, `8B0E7` / `D22AC` weekday reads; regular generator `2BF270`, season grid `E57C40`, template pair at loaded ROST root `+28/+2C`. These need a loaded franchise/template, not a new SEGA predicate. Full presets require the builder's 2026 template as well as XBE season changes. No active hook exists for the refused franchise-2026 rule kernel. |

Clock, momentum, screen timing/hooks, dynamic kickoff, read option, QB spy,
deep zone and 7-on-7 need gameplay actors or practice/play state; they do not
run their gameplay policy in the still-logo wait. Guardian needs a helmet
scene, scorebug needs the game HUD, weekly prep needs a franchise fixture,
and the MyCareer HUD needs an active career/game. Their early common
loaders/settings/readers are included above. This distinction is based on
hook conditions and bounded routes; the asynchronous resource pump is not
implemented as an Xbox loader in this harness.

## Series inputs and separate MyCareer findings

`tests/nfl2k5_b661_series.py` runs the production data compilers on the private
primary ROST and ATL PLAY in memory: position pools, kickoff alignment and
return assignments, depth roles, screen timing D, the 2026 regular/preseason
templates, and the larger roster migration when selected. It reparses through
the existing native series fixture. The initial executable-only attempt fed
retail ROST to the larger-arena runtime and faulted at `0x77AE6`; that attempt
is not a valid player's built-disc input and is excluded from acceptance.

Two separate pregame-creation limitations are PROVED, neither a loop nor the
reported after-Berman hang:

1. The fully extended build with migrated ROST has team metadata version 2.
   MyCareer `mode_create` checks it against 1. In this exact extended union,
   `0x14E7C47: cmp byte ptr [eax+0x19B],1` and
   `0x14E7C4E: ja 0x14E7CF3` return “Roster is full.” to the entry menu.
   No new player or match is created. The test checks this native refusal.
2. In simwin66, fresh signing uses 54 in `tools/mycareer_mode/runtime.c:594`
   (`0x14E3CB6: push 0x36`),
   while the installed Practice Squad append at `0xC3EE0` uses its real limit
   (`0x3EE10C`), 53 for the initialized regular-season club. The club has 53
   players. `0x14E3DAB: call 0xC3EE0` returns zero; its result is not checked
   before the following native calls. The fresh-sign sequence still
   reaches `capture` / the Apartment. Native `resolve_team` finds no membership,
   leaving career state 4 and club `FFFFFFFF`; `mode_next_fixture` returns 374.
   “Play next game” therefore has no fixture. This is an independently
   reproducible creation problem, before the requested transition.

For the active-career series test, a separate, explicit **existing signed
career input** makes room with native `0x2BF9A0`, appends through the installed
`0xC3EE0`, and resolves membership natively. It does not change executable
instructions or manufacture player readiness. The original fresh-sign result
is retained in the receipt. This input is a limit on the proof, not a product
fix or evidence that fresh creation works. The series then runs the real
outer frame and its 27 phases; the kickoff command is supplied at `0xB6F30`.
This proves that command returns and reaches state 14. It does not prove
when a CPU-controlled kickoff decides to issue the command.
The fully extended active-career creation path cannot reach this window with
its version-2 roster; the no-career extended frame/readiness/camera/return
cases and the explicit native creation refusal are recorded separately.

These findings need a separate MyCareer creation correction: honor the
installed append capacity after franchise initialization, preserve ownership
when append fails, and validate the larger-roster owner before accepting its
metadata. Simply changing the metadata comparison from 1 to 2 would also
require auditing reserve traversal in `resolve_team` and the signing path.
H2 does not alter those game instructions as a claimed Berman/SEGA fix.

## Beta 63 through 66 interpretation

The census covers earlier owners retained by the current build. Beta 64 kept
the 2K5 beta-63.1 runtime; beta 65 added accelerated clock and MyCareer work;
beta 66 changed camera v6, MyCareer frame scheduling, paired-book identity and
music collections among the audited surfaces. The current kickoff v6 already
lets the native catch/kneel task finish; the v6 native suite retains retail
and historical controls. Its touchback receipt reaches the next scrimmage
setup, not a simulated first scrimmage snap.

The older runtime scorebug provides a real historical wait control:
`FCE56 -> 42C00 -> 44DC0 -> 28F40 -> 33660`, repeating at `3367A` while a GPU
fence is pending. The installed HUD-scoped binding returns without that
eviction path under the same synthetic pending fence. The seven-test
`test_nfl2k5_scorebug_freeze_v2.py` suite checks old, current and native
controls, missing HUD, wrong resource type and re-entry. That earlier fix is
already installed in this branch; it is not a newly established cause of
Jeffrey's disc. Rebuilding from the original source and obtaining the exact
Build summary distinguish old installed patches from a new failure.

## Noah's first checks and exact witness questions

**Jeffrey / after Berman:** first rebuild the same recipe from the original
source with **Dynamic kickoff off**, keeping the game mode, teams and roster
the same. This targets the only added readiness policy directly at the
reported boundary; its implication in Jeffrey's hang is HYPOTHESIS. If
Dynamic kickoff was already off, this experiment cannot identify it. Next
try **Broadcast camera off**; then **Separate offensive and defensive
playbooks off** if selected. For an active MyCareer, try **MyCareer off** in
an otherwise equivalent normal match before interpreting generic kickoff
results as a MyCareer result. The two fresh-creation limitations above need
their own reproduction, not a claim that turning off one option fixed audio.

Question to relay to Jeffrey (not sent): “Which beta last let you play? Please
paste the failing disc's Build summary and say whether this is Play Now,
Franchise or MyCareer, whether you loaded an older roster/franchise, and
whether MyCareer Supersim is on. Does an otherwise identical fresh build with
Dynamic kickoff off get past Berman and through the first scrimmage snap?”

**jrolling / SEGA:** first try **Music playlist / shuffle off**, if it was on,
in a cold boot of an otherwise identical rebuild. It has startup/menu and
resource calls where game-only policies are inactive. This priority is a
HYPOTHESIS, not a failed native playlist test. If it was already off, first
try **16 reserves off**, then **two extra created teams off** if selected;
keep a separate copy of any existing saves and test the built-in roster.
If still stuck, test **MyCareer off**. Added songs, custom art and a restored
emulator state are distinct inputs that the scalar I/O harness does not
reproduce. No save deletion is requested.

Question to relay to jrolling (not sent): “Which exact experimental option or
options did you turn off to get past SEGA? Please paste the failing Build
summary, including MyCareer, playlist/added songs, 16 reserves and extra
created teams, and say whether this was a cold boot or a restored state.
Does the otherwise identical build with playlist shuffle off reach the title?”

For either persistent failure, the stopped main-thread PC plus `B09584`
(pending loader queue), `E602B4` / `E602B8` (football phase/state), `B616C0`
(camera state), and the selected-play chain `[E60280]+0xC -> +8` would select
the matching bounded check. Repeated audio alone does not identify an owner.
Played boot, Berman playback, kickoff and first scrimmage snap remain
UNWITNESSED. Full asynchronous resource/device loading and user saves remain
outside offline reach. No speculative game wait is shortened or bypassed.

## Verification

Commands run standalone from this worktree with `PYTHONPATH=.`. The final
validation receipt, `docs/nfl2k5_b661_validation.json`, retains the exact
commands, unittest output summaries, durations and log hashes for all
completed suites. Earlier failed fixture attempts are explained above and
are not counted as passing runs.

| Command (after `PYTHONPATH=.`) | Output |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_b661_transition.py --record` | `Ran 11 tests in 364.306s`, `OK` |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | `Ran 115 tests in 1482.404s`, `OK` |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | `Ran 127 tests in 1673.915s`, `OK` |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | `Ran 29 tests in 348.632s`, `OK` |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | `Ran 388 tests in 2098.059s`, `OK` |
| `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | `Ran 23 tests in 42.961s`, `OK` |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v6.py` | `Ran 9 tests in 127.723s`, `OK` |
| `python3 tests/mod_editor/test_nfl2k5_supersim_live.py` | `Ran 29 tests in 3412.958s`, `OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_budget.py` | `Ran 5 tests in 4.173s`, `OK` |
| `python3 packaging/repin.py --apply` | `applied 0 pin update(s)` |

All 32 standalone suites passed, totaling 1020 tests. The baseline series completed 3 plays in 422 presented frames and 3376 complete native updates.

The new baseline series receipt matches the shipped beta-66 native series
receipt exactly.

The remaining owner suites cover abilities, accelerated clock, the boot logo,
deep zone, franchise-rule refusal, guardian, jukebox, momentum and collisions,
music metadata/playlist/contexts/library, MyCareer settings, paired books,
camera v6, QB spy, read option, screen hooks/timing, scorebug runtime and its
historical wait, and weekly prep. Their individual results are in the
validation receipt. The full existing Supersim suite uses retail plus the
MyCareer writer; its multi-play receipt is a baseline, not an all-options
build. Composed-preset results are recorded separately in
`docs/nfl2k5_b661_transition_receipts.json`.

No production writer or protected file changed. The current reservation
manifest verifies its source hashes and section digests in the oracle suite;
no manifest regeneration or WIRING change is needed. Repin is run again
immediately before each explicit-path commit and reports zero updates.

## Delivery

The sandbox makes this worktree's Git metadata read-only. New explicit-path
commits use temporary Git metadata and are delivered in `ASTRA_H2.bundle`,
including the retained `d1bfbed2` commit, with prerequisite `1d38df5e`.
The original worktree branch is left at `d1bfbed2`; its visible file changes
are preserved. The bundle can be fetched into the integration repository and
its commits reviewed or cherry-picked there. Handoff inputs, the private
`extracted` link and the unrelated existing `WIRING.md` are excluded.

The delivered changes are the header-mapping fixture correction, composed
preset/resource harnesses, bounded missing-input checks, exact derived
receipts, this report and the RC91 beta-66.1 changelog bullet. No game patch
is presented as a proved fix for either reporter's hang.
