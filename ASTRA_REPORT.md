# Beta 66.1 H2: Berman / SEGA transition research

Branch: `astra/b661-game`. Source: beta-66.1 stack `1d38df5e`.
Research checkpoint; final matrix results are recorded below as they complete.

## Finding and evidence boundary

TheWildJeffrey reported “freezing right after Berman and repeating audio.”
jrolling2003 reported being “stuck on the sega screen”; lt9608 reported “it kept
freezing, and the new kickoffs and things didn't show up.” These reports do not
identify a Build summary, source-disc identity, game mode, saved settings or
the CPU's stopped instruction. **No reported console hang has been reproduced
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
outside Git. Scratch contains text logs only.

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

## Verification

Completed so far, standalone with `PYTHONPATH=.`:

- `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py`: 23 tests, OK.
- `python3 tests/mod_editor/test_nfl2k5_kickoff_v6.py`: 9 tests, OK.
- `python3 packaging/repin.py --apply`: 0 pin updates (no pinned writer changed).

The composed transition matrix, owner-native suites and doctrine gates are
still running at this checkpoint. Final results, Noah's precise isolation
order and the witness questions follow in the final update to this report.
