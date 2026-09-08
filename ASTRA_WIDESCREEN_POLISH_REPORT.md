| Consumer | Address / evidence | Class before polish | Fixed / open |

Public path notation: `<home>` and `<media>` identify the original local home and mounted input directories. Recorded hashes, measurements and outcomes are unchanged.
|---|---|---|---|
| Active world projection | `2AC80 -> 2B510`, active `A6AFC0`, projection `+0`, composite `+F0` | Correct in v2 for the first field: widened matrix, retail principal point | PROVED: retained hor+; native composite rebuild now used. |
| Second interlaced field | `2B510`, `2B5B0`, matrices `+130/+170` | Stretched: v2 only corrected the first field | PROVED FIX: corrected x columns in both fields, native y difference retained. |
| Projection-dependent screen plane | `2A9E0`, camera `+1B0` | Misplaced: rebuilt before the projection changed, then left stale | PROVED FIX: rebuild from the corrected projection. Exact visual manifestation still unwitnessed. |
| General objects and model culling | `215A0 -> 2ADC0`; `28B7F0` gets active at `28B7FE` | Correct: active horizontal normals already widened in v2 | PROVED: real sphere cull accepts newly visible edges and retains vertical/depth rejection. |
| Projected/slanted shadow culling | `1C3190`, rebuilt local copy; camera load `1C32FB` | Culled early: the local copy regains retail frustum after its view setter | PROVED FIX: cull against the camera activated for this pass. |
| Sideline players / cheerleaders | String bindings in `11A0A0`, model route `28B2A0 -> 28B7F0` | Correct at engine consumer: active widened frustum | PROVED route; OPEN runtime pop-in witness. Specific crowd mesh families are not all bound to this route. |
| Saved-camera object / stadium branch | `913B0`, saved active at `913E8`, `90190 -> 215A0` | Correct: transformed saved copy, no intervening rebuild before cull | PROVED route; asset-specific seams and LOD transitions OPEN. |
| LOD / camera-distance reports | `66A60`, `913B0`, `28B7F0`, `9B350` | Correct for unchanged vertical size: reads retail `s` at `+270`, not a clip width | PROVED input preservation. HYPOTHESIS: transitions look natural on a wide display; witness required. |
| Sky panorama and full-target tint | `9E540`, `9DD60`, sky camera `A87B60`, `9E1A0`, `9DEA0` | Clipped and stretched: sky quad was pillarboxed; horizontal UV angle used old `s` | PROVED FIX: full-width sky/tint exemption and horizontal `s/F` load at `9E1BC`; vertical `9E110` remains retail. |
| Far stadium / sky geometry | `9DE10`, `9CEF0 -> 9CCA0 -> 9B770 -> 21860` | Correct projection route: view/near/far setters followed by activation | PROVED widened matrices and cull path; OPEN mesh, texture-wrap, fog and dome seams. |
| Projected billboard type 2 | `7F840 -> 7EC40`, projector call `7EC59`, then pixel camera `66950` | Misplaced and clipped: projects saved active wide matrix then compresses x again in HUD | PROVED FIX: undo the first x transform at this call; full-world marker clip. |
| World billboard type 1 / depth-only probes | `7F5B0`; `531D0`, `85D20`, `85E30`, `7F300` | Correct: world-space geometry or depth-only result; no second pixel-HUD x transform | PROVED: projector itself stays native; these callers are not redirected. |
| Passing/controller icons, foot/head marker queue | `FA270` calls `FA2A1/FA31E`; `FA0B0`, atlas draw `F97F0`; HUD setup `64670` | Misplaced and clipped: active wide pixels fed to pillarboxed HUD | PROVED FIX: undo x at both projections; retain full world clip and normal glyph size. Exact icon variants require witnesses. |
| Player name/number labels | `F9950`, cull call `F999D`, camera built by `66950` | Culled early / misplaced: HUD cull clamps visible edge labels to the inner window | PROVED FIX: marked world-marker HUD expands horizontal ortho cull bounds as well as its clip. |
| Auxiliary line/replay-marker callback | `32C830`, calls `32C895/32C8AC`, activates `CB7220` and draws `EF8A0` | Misplaced: two active-camera projections followed by a separate HUD | PROVED numeric FIX at both calls. HYPOTHESIS: exact replay-marker scene binding; no direct caller in the corpus. |
| Player circles / controller star / world play art | `F9320 -> F8880`, star draw near `64F21`, camera basis helper `2AF70` | Correct: world-space geometry goes through active GPU matrix | PROVED geometry route. OPEN exact defensive-line / route-art variants in play. |
| Play-call diagram and its icons | `144360`, `144BA0`, camera `BD7030`; `181010 -> 1650A0` | Correct: icon projector reads original retail diagram camera, then pillarboxed pixel HUD | PROVED preservation: diagram and clip remain pillarboxed. The old claim that all diagram icons are 3D billboards was too broad. |
| Offscreen direction arrows | `F82C0 -> F94D0` | Uses active visibility but retail target-edge anchors | PROVED inputs; anchors remain inside the 4:3 HUD convention. OPEN whether any arrow variant needs a separate world-edge anchor policy. |
| Kick meter | `BA940`, HUD constructor `66930`, anchor arithmetic `BAAAD..BABDD` | Correct: screen-anchored HUD, including fixed margins; not a world-point projection | PROVED retain pillarbox. Existing optional HUD-layout edit at `BAB52` remains disjoint. |
| Pre-play, live, field-goal and punt cameras | `5F460`, `5F760`, camera table `4F03F8`, constructors `66720/66B20` | Correct: full-width perspective activation; old lens is source data | PROVED shared route; OPEN exact transition witnesses for states 9/16 and kick states 8/10/11. |
| Cutscenes and letterboxed replays | `54E20`, `54EF0`, `111E00`, `57CE0`, shared activation | First field correct; alternate field and sky could stretch/clip | PROVED common fixes, including full x target with shorter y target. OPEN replay-camera and bar witnesses. |
| Studio / menus with 3D backgrounds | `69030`: HUD `A83F20`, world `A841D0`; previews `346890/35B490/35B780` | World uses perspective; UI uses retail 640x448 layout and pillarbox | PROVED geometry split and common fixes. OPEN art/layout witnesses for individual previews. |
| Scoreboard / scorebug | HUD `66930`; existing `nfl2k5_scorebug_ingame.py`, `nfl2k5_hud_layout.py` | Correct by design: 4:3 anchors, not a field-bound world projection | Retained; scorebug owners compose in both gates. OPEN visual placement witness. No `widescreen_hud` option added. |
| Packed camera scissor | `2A6E0 -> +200`, consumed by `2B5B0` | Clipped: a one-pixel interval could round to zero/invert | PROVED FIX: exclusive right endpoint is at least left+1, under all four x87 rounding modes. |
| Render-list clip reset / SDK viewport | `2ACD0`; SDK `422130`, `423230` | Correct physical-target/reset values, not an old horizontal cull | PROVED distinction: `2ADC0` is sphere culling, **`2ACD0`** resets clipping. Physical 720/480 constants stay native. |
| Fades, raw ortho art, render-to-texture | `119E0`, `11A80/AF9300`, `57CE0/B28730`, `D9FA0`, `29880`, target census below | Known unit fades correct; some raw art may be stretched or an in-frame texture target may be clipped | Known exemptions retained; OPEN unknown asset semantics and non-unit effect quad. No unsupported global constant rewrite. |

EXPERIMENTAL / UNWITNESSED. Completed 2026-09-06 against stack base
`f371972f4a17cecf654c019d5c6ff3a3c32c7caa`. No emulator, GUI, audio or network
was used. “PROVED” means executable bytes, corpus data flow or bounded CPU
execution, never a claim that Noah has played this build.

This extends the existing `widescreen=True` family to v3. The regular HUD
keeps its existing apparent size. The new behavior fixes proven inconsistencies
between world projection, shadows, projected HUD markers, sky, clipping and
interlaced fields. The report deliberately leaves asset-specific hypotheses
visible instead of treating a CPU proof as a visual acceptance test.

Evidence and implementation
---------------------------

The audit used the read-only USA corpus at
`<home>/2k-football-mod-tools/research/functions/nfl2k5/functions.tsv`
and its `pseudo_c` shards, then checked hook instructions in the retail XBE.
The companion [byte receipt](docs/mod_editor/widescreen_polish_receipts.json)
includes exact corpus file names, body ranges and caller/callee lists for the
critical functions and all 22 target-setter callers. The RC85 changelog,
existing Astra reports and the hub's `WIDESCREEN_2026-09-03_NIGHT.md` supplied
the prior assumptions; the audit table supersedes their blanket claims about
active-camera consumers and billboard alignment.

The USA XBE is 11,948,032 bytes, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Only this executable and small synthetic camera/stack fixtures were loaded.
No whole disc image or archive pack was read into memory.

For 16:9, `F=32/27`, `1/F=27/32`, `K=56.25`. For 16:10, `F=16/15`,
`1/F=15/16`, `K=22.5`. These compensate the 720x480 framebuffer, so using
4/3 as the denominator here would be incorrect. The full-world matrix keeps
its principal point at frame x=360. The ordinary HUD maps
`x -> 360 + (x-360)/F`, giving an inset clip of 90..630 for 16:9.

`2AC80` copies 0x2B0 camera bytes into `A6AFC0` and stamps that camera into the
render list. Each activation rebuilds native outputs before transforming
them, so a saved active copy can be activated repeatedly without compounding
the stretch. Original source objects remain unchanged. Runtime tags occupy
the existing `+24C` rect padding; the constructors initialize it and the
audited math does not consume it as a coordinate. No runtime state is written
to executable code. The known diagram/fade tags are retained, with tags for
transformed copies and full-world pixel HUDs added.

`2B510` has a second projection/composite for interlaced rendering, only when
`[A6A9CC]==1` and `[A6AA58]==[A6AA20+4*[A6AA18]]`. V3 updates its x columns
under that exact condition. `2B5B0` selects `+F0` or `+170` using `A6AA00`;
the CPU proof executes that selection and the packed GPU clip writes.
The native `31110` matrix product replaces the old unrolled x-only product.
`2A9E0` then rebuilds the screen plane from corrected projection values.

The four direct sphere-cull callers are `215A0`, `F9950`, `1C3190`, and
`28B7F0`. General-object wrapper callers `21860`, `85A10`, `951D0`, `960E0`,
`96B90`, `985B0`, and `121AE0` use active cameras. `90190` receives a saved
active copy from `913B0`. V2 already widened the normal full-world horizontal
pair, so replacing every cull or every lens read would have been unjustified.
The shadow pass is different: its view setter `13E770` rebuilds the local
frustum, then it activates a corrected copy but culls against that local
retail frustum. The seven-byte load at `1C32FB` now selects the active copy.

LOD helper `66A60` reports retail `s`, with an optional existing ratio. Its
callers include `13370`, `5E120`, `5F760`, `913B0`, `9B350`, and `28B7F0`.
The latter distance thresholds use distance and lens size, not an independent
old 640-pixel horizontal rejection. Keeping `s` preserves vertical image
size and camera behavior. Whether the exposed edge geometry reveals an
unattractive LOD switch is a separate visual question.

`2AB40` projects through `+F0`, divides by homogeneous depth and returns
reciprocal depth in x87 ST(0). Its direct caller functions are `531D0`,
`5B070`, `7EC40`, `7F5B0`, `85D20`, `85E30`, `887D0`, `DADE0`, `F82C0`,
`FA270`, `FFE90`, `112F00`, `1650A0`, and `32C830`. A global change would
damage depth-only and original-camera consumers. Five proven double-transform
calls instead use a wrapper: for a transformed camera, output x becomes
`360+(x-360)*F` before the HUD applies its own inverse. The wrapper preserves
y/z/w, the native reciprocal depth, stack cleanup and callee-saved registers.
Original source cameras remain a no-op through these wrappers.

Alignment alone is insufficient. `66950` constructs a pixel HUD with retail
target fields; ordinary pillarboxing would clip correctly aligned markers
at x=630, while the world extends to x=680. Its final rect-setter wrapper
marks only HUDs derived from a widened full-frame perspective source, checked
by source tag, projection type and exact packed raw/inset clip. Such HUDs
retain world clipping while their glyphs still use the inverse scale.
Their horizontal ortho cull bounds expand by F, keeping unit plane normals
and sphere-radius semantics. This prevents `F9950` from clamping a visible
edge name/number to the old window. Diagram/subwindow HUDs keep their own
pillarboxed clips and ordinary scorebug/menu cameras never receive this tag.

`9E540` saves the active world camera; `9DD60` makes the screen-space sky
camera from its target. `9E1A0` activates that sky camera and computes
horizontal texture angles from saved `s`, bypassing the widened matrix.
The new wrapper scales only that horizontal load. `9E110` still uses retail
`s` and target height/width for the unchanged vertical angle. Full-world sky
and its `9DEA0` tint quad cover the world target; a subwindow remains
pillarboxed. The separate `9DE10` far 3D pass already activates its rebuilt
camera and follows the shared correction. This proves width/angle coherence,
not texture continuity at every stadium's panorama seam.

Viewport and scissor census
--------------------------

Every direct caller of target setter `2BB00` in the corpus is accounted for
below. Its target feeds `2B510 -> 2A6E0`, then the GPU consumes packed
`+200..+20C` through `2B5B0`. “Conditional” is the proven geometric dispatch,
not an assertion about every texture or scene bound to that function.

| Setter caller | Target origin / consumer | Treatment and classification |
|---|---|---|
| `119E0` | Copies scene target for fade | Known fade route; unit geometry remains full-target, correct. |
| `11A80` | Full-target color camera `AF9300` | Explicit exemption, correct. |
| `29880` | Texture dimensions from surface metadata | `0..W` texture target, generally untouched; in-frame subrect semantics OPEN. |
| `32C10` | Integer rectangle copy/viewport utility | Conditional classification of resulting target; no global width rewrite. |
| `36330` | Derived texture/special-pass bounds | Physical target sizes retained; scene binding OPEN. |
| `36700` | Derived texture/special-pass bounds | Same conditional behavior; no unsupported screen-width assumption. |
| `36C90` | Derived texture/special-pass bounds | Same; render-target appearance OPEN. |
| `533B0` | Copies saved active target for a special pass | Subsequent activation rebuilds coherently; specific effect OPEN. |
| `5F460` | Slot camera target/letterbox layout | Full x perspective hor+; subwindows pillarbox; y retained. |
| `66720` | Full-screen constructor via `66670` | Native `(40,16)..(680,464)`, correct hor+/HUD split. |
| `66850` | Native EEPROM aspect handling | Retail alternate target shrink retained; witness recipe leaves EEPROM aspect flags zero. |
| `66950` | Pixel HUD copies source camera target | FIX: marked world HUD keeps wide clip/cull; other HUDs pillarbox. |
| `7F840` | Billboard pass copies active camera target | FIX: projected type 2 follows the marker wrapper and pixel-HUD rule. |
| `9DD60` | Sky target copied from saved world | FIX: full sky fills world width; subwindow sky pillarboxes. |
| `D9FA0` | Saved target converted into non-unit effect quad | Reads target dimensions, not hardcoded 640; OPEN effect binding and desired coverage. |
| `FB330` | Layer target copy | Conditional activation; OPEN exact layer content. |
| `FFE90` | Lineup insert `BA3550`, original camera pixel projection | Retail coordinates for HUD placement; preserve existing subwindow framing. |
| `144BA0` | Clamped play-diagram window | Forced pillarbox; original camera icon projection matches. |
| `346890` | Preview/layout window | Subwindow projection and clip transformed together; artwork witness OPEN. |
| `35B490` | Preview/layout window | Same. |
| `35B780` | Preview/layout window | Same. |
| `364510` | Integer rectangle/viewport utility | Conditional target; no independent 640-width lens patch. |

Other viewport writes are not hidden culling rules: `2ACD0` restores the
render-list clip/cache defaults using `4E6030/4E6040` at list boundaries
(`32F80`, `331A0`, `335D0`). A subsequent camera submission reinstalls its
own clip. SDK `D3DDevice_SetViewport` at `422130` has callers `424260` and
`42A9E0`; `D3DDevice_SetScissors` at `423230` is called by that viewport
routine. Those are physical backbuffer/render-target bounds. Scaling all
720/480 or 640/448 constants would corrupt render targets and HUD framing.
No claim is made that static direct-call census resolves all dynamic asset
bindings.

Exact byte and ownership receipt
--------------------------------

[widescreen_polish_receipts.json](docs/mod_editor/widescreen_polish_receipts.json)
contains full before/after hex and SHA-256 for every site for both aspects,
all 23 immutable context pins, code-label addresses and the section digest
edit. Offsets below refer to the retail USA file, not a disc offset.

| Site | VA | File offset | Reserved bytes |
|---|---|---|---:|
| Nine immutable floats | `10254` | `254` | 36 |
| Existing reserved code cave | `46EE0` | `36EE0` | 832 |
| Activation call | `2ACA1` | `1ACA1` | 5 |
| Billboard projection call | `7EC59` | `6EC59` | 5 |
| Foot marker projection call | `FA2A1` | `EA2A1` | 5 |
| Head marker projection call | `FA31E` | `EA31E` | 5 |
| Auxiliary marker call 1 | `32C895` | `31C895` | 5 |
| Auxiliary marker call 2 | `32C8AC` | `31C8AC` | 5 |
| Shadow camera load | `1C32FB` | `1B32FB` | 7 |
| Pixel HUD final setter call | `66A52` | `56A52` | 5 |
| Sky horizontal lens load | `9E1BC` | `8E1BC` | 6 |

Code occupies **831 of the existing 832 reserved bytes**, followed by one
`CC` byte. Total owned spans are 916 bytes; 892 change, plus 20 changed bytes
in the `.text` digest at file offset `394`, for **912 actual file differences**.
The XBE length is unchanged. There is no new allocator request, RX/RW/RO
section or budget row. The existing cave reservation, not an oracle
“unknown”, authorizes the space. The constants do not overlap the throw
arc table at `10310`. The cave contains code only; temporary values live on
the runtime stack and in the active camera's existing data storage.

The final 16:9 XBE-only SHA-256 is
`81d6e16c25ca7ea1014d0ced915f910f5d354eaeabeb9adfcbb6956e2a0b54f8`.
The 16:10 SHA-256 is
`57748b161b8946c21788ed6a5f5c3f98c772e6456b43da77136a95b7c650fb93`.
These are single-family retail-base receipts; a composed disc has different
hashes. The common code-cave SHA-256 is
`31e272048f88b60121d646d6c15f75b95ef22a1035696aaeff25838a9ecc09d7`.

`status` validates all owned sites and context before accepting applied
state. `apply` is an exact no-op for the same complete v3 aspect. Partial
installations, changed context, another aspect, and old v1/v2 installations
refuse before any mutation. Rebuild old widescreen discs from a clean base;
there is deliberately no permissive in-place migration or new uninstall API.

Validation completed
--------------------

All tests below ran standalone with plain Python, with no skips:

| Command | Result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_widescreen_polish.py` | 13 passed, 4.563 s |
| `python3 tests/nfl2k5_widescreen_test.py` | 8 passed, 1.169 s |
| `python3 tests/nfl2k5_camera_test.py` | 10 passed, 0.784 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 59 passed, 158.823 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 71 passed, 241.588 s |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | Passed; existing budget table, no added request |
| `git diff --check` | Passed |

The new suite executes the real USA activation, matrix, plane, projector,
pixel-camera constructor, sky lens/vertical-angle, sphere-cull and GPU packet
code under Unicorn with a 10,000-instruction bound per invocation. Executable
`.text` is RX in those cases. Both display aspects, raw/inset/subwindow targets,
matching/nonmatching interlace modes and four rounding modes are exercised.
Source bytes, native non-x components, stack cleanup and saved-register
behavior are checked. An end-to-end marker lands on the exact widened world
pixel; restoring the old HUD cull bounds rejects it, while the fixed bounds
accept it and still reject an offscreen label. The harness consumes each
projector's reciprocal-depth return just as the retail callers do.

Manifest coverage uses the production `Recorder.observe` on the real patched
XBE and requires each entire owned span, including unchanged bytes, to belong
to `nfl2k5_widescreen`. Receipts now expose `file_offset` as well as the old
`offset`, so the recorder reserves the full 832-byte cave rather than only
changed runs. Every resulting section digest is checked. The protected
committed manifest was not regenerated; Claude's integration instructions
are in [WIRING.md](WIRING.md).

Both XBE gates compose all existing owners. Their reverse order now defers
the complete widescreen installation until after the allocator owners, then
requires the same bytes and exact replay. This test-only fixture preparation
does not add a product uninstall operation. Both gate setup paths explicitly
check complete v3 status/replay after composition.

The existing Build engine was exercised with a real retail XBE in a resolved
`TemporaryDirectory`: `BuildPlan(widescreen=True)` produced exactly the same
v3 bytes, inspection reported applied, and the source stayed unchanged.
Basic/Advanced remain false and Experimental remains true. The Build engine
currently drops the nested byte receipt from its summarized step; retaining
that receipt and refreshing protected UI text are specified in WIRING.

CPU fixtures map about 15 MB plus small stacks; the synthetic writer fixture
is about 3.3 MB and the composed executable about 12.3 MB. No new test needs
a whole image/pack, GUI, audio or an external service. No disposable disc was
built: available space was approximately 103 GB during the build decision,
so a 6.3 GB copy would have broken the user's 100 GB free-space floor. The
small XBE test copies were deleted on every exit path. Scratch contains only
small logs/research/receipt material, currently under 1 MB and well below
200 MB. A full-disc Build witness remains for Noah.

EXPERIMENTAL Build-tab recipe
----------------------------

For the first comparison, use a clean retail USA disc as source and a new
output name such as `ESPN NFL 2K5 - widescreen polish v3 EXPERIMENTAL.xiso.iso`.
In a fresh Build tab, leave the other options off and enable **Widescreen
16:9** (the caption after wiring is **Widescreen 16:9 (experimental)**).
This existing checkbox installs all eleven v3 sites; there are no separate
shadow, sky, marker or interlace switches. Keep the camera override off for
the first comparison so the native Standard and Far views are distinguishable.
Build a separate control from the same source with this checkbox off.

The equivalent existing BuildPlan recipe is:

```python
BuildPlan(
    source="/path/to/clean-USA.xiso.iso",
    target="/path/to/widescreen-polish-v3-EXPERIMENTAL.xiso.iso",
    widescreen=True,
    name="Widescreen polish v3",
    notes="EXPERIMENTAL / UNWITNESSED; keep HUD 4:3; witness list in report",
)
```

For a composed follow-up, choose the existing **SOFTDRINK Experimental**
preset, verify Widescreen 16:9 is checked, then build from the same clean base.
The preset also selects unrelated experimental features; record its complete
Build receipt so any failure can be compared with the isolated build.
Leave EEPROM widescreen/letterbox flags at zero and set xemu
`[display.ui] aspect_ratio = '16x9'`. Use a 4:3 display setting for the retail
control and 16:9 for the candidate. Do not layer another FOV/widescreen patch
over this family. The backend retains tested 16:10 support, but the current
Build checkbox selects 16:9 only.

Before each disc build, check free space and reserve the full source-size
copy plus temporary workspace while keeping **more than 100 GB free**.
Disposable acceptance discs belong in a `TemporaryDirectory` and must be
deleted afterwards. No persistent witness disc was created by this session.

Noah's witness list
------------------

Record build/source hashes, selected patches, display/EEPROM settings, teams,
stadium, weather, camera and quarter, plus a short clip or comparison frame
for each item. These are requested witnesses, not reported successes.

| Exact scene/action | What fixed looks like |
|---|---|
| Practice scrimmage, Standard camera; run parallel to each sideline with teammates crossing both outer strips | Newly visible players, sideline staff and their shadows enter continuously; no disappearance at the old inner boundary. Repeat in Far. |
| Same play, receiver crossing near x=630..680 and the symmetric left strip; hold passing icons and switch controlled player | Passing icon, controller indicator, foot/head marker and name/number stay centered over the same player. Labels do not jump to a bottom corner and glyphs keep normal size. |
| Pre-snap play selection, formation/diagram preview, show/hide routes and defensive assignments | Diagram remains inside its window; its icons and lines agree. World play art tracks the field, without lateral drift after closing the diagram. |
| A deliberately offscreen receiver on both sides while the camera pans back onto him | Direction arrows remain usable; record any arrow that follows an old inner edge or points incorrectly. This anchor policy is still open. |
| Field goal from both hash marks, PAT, then punt and punt return; watch pre-play to live transition | Posts/field widen without vertical zoom or a lateral snap; kicker/returner markers track correctly; kick meter remains readable and proportional. |
| Outdoor day game, e.g. Packers at Lambeau; pan a replay across both horizon edges and through the panorama wrap direction | Sky and tint reach the world edges, no vertical side strips, abrupt sky-to-stadium mismatch or newly exposed texture seam. |
| A domed stadium, e.g. Lions at Ford Field; low-angle replay toward roof and end-zone stands, then an outdoor night replay | Far geometry, roof/dome and crowd are stable at the new edges; no fog/tint strip or material seam. Asset-specific results are open. |
| Pause into instant replay after a sideline catch; change replay cameras, scrub, show controls/markers, enter and leave letterboxed views | No lateral marker offset; bars keep their height and span the intended image width; no field-to-field width shimmer. Confirm the auxiliary marker callback's actual scene. |
| Let the pregame/player-introduction cutscene and halftime/postgame studio run; also inspect menu/team/player 3D previews | 3D subjects retain proportions; HUD/menu text remains 4:3-sized; no sky strip, clipped inset or transition-width pulse. |
| In-game scorebug during a score, timeout and possession change, plus kick-meter use | Scorebug and meter remain within the intended HUD window, legible and proportional. No new full-width HUD arrangement is expected. |
| A camera pan with a textured vertical object, both native field modes where available | Both interlaced fields have identical horizontal geometry; no alternating width/edge jitter. GPU CPU proof does not certify xemu presentation. |
| Fade to/from replay, menus and gameplay, including any special color/effect overlay encountered | Full-scene fades cover both outer strips. Capture the non-unit effect-quad case if it leaves a strip. |

Known gaps and handoff
---------------------

No result above is witnessed. The audit proves shared data flow, not every
indirect asset binding: crowd subsets, dynamic preview content, auxiliary
replay-marker identity, offscreen-arrow policy, `D9FA0` effect semantics and
render targets whose rectangles resemble screen windows remain open. These
are explicit hypotheses, not claims that every artifact is eliminated.
Native EEPROM widescreen behavior and real GPU/presentation timing are not
covered by the 16:9 recipe. No PS2, 4K/HD asset or arbitrary-aspect support
was added.

Protected files remain unchanged. WIRING supplies the exact dispatcher,
BuildPlan/preset, four-status, UI, allowlist, runtime import and manifest
handoff. The existing flag already reaches this backend; protected work is
the label/receipt/manifest integration, not a missing runtime feature toggle.
Git delivery follows the brief's explicit-path commit or isolated-metadata
bundle fallback, without pushing or including `ASTRA_BRIEF.md` or `.scratch`.
