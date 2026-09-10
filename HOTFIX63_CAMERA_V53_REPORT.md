# Beta 63.1 hotfix: Broadcast camera v5.3, the mount clears the near stands

Branch `astra/hf63-camera-clip` from tag `beta-63` (9c17c538). One bug, numbers only, no new feature, no preset
or wiring change. EXPERIMENTAL / UNWITNESSED: nothing here was played; the proof is the native solver in Unicorn
and the retail stadium geometry. Written 2026-09-09.

## The field report

maumau78 on beta 63 (#2k5-general, 10:51 then 13:16): "Broadcast CAM on the last release is fire!" and "only issue
is that on right side will clip over crowd and stadium structure ... but it really add a lot of depth to the game",
with a frame from WAS at NO (the Superdome, the offense at the NO 15 driving toward the left end zone, 2nd and 15).
Noah's design verdict stands: v5.2 (a559f4b6) is the accepted look, "the last-year NFL TV broadcast look, centred".
Only the intrusion into the crowd and stadium structure is fixed here.

## Where it clips: positions and numbers

v5.2's Broadcast record is a type-2 (following) descriptor: `BROADCAST_VALUES = ((400, 0, 250), 80, (5250, 1650,
200))`, look-at 4 m toward the camera side and 2.5 m ahead of the ball, mount offset 52.5 m toward the camera side,
16.5 m up, 2 m along the field (all centimetres in the game; the camera side is +x, y up, z along the field with
the offense direction flipping the z terms). The native solver `FUN_0005f760` computes, every frame,

    look-at = ball + (400, 0, 250 x dir)                 (clamped to the camera's look-at box; the template's setup
                                                         callback A40C0 caps its height at 100 cm, nothing else)
    eye     = look-at + smoothed offset (5250, 1650, 200 x dir)   = ball + (5650, 1650, 450 x dir)

so the mount rides with the ball ACROSS the field as well as along it. The eye's world position is therefore
`(ball.x + 5650, 1650, ball.z + 450 x dir)`. Against the retail stadiums:

- The stadium scenes were read through the Stadium Studio's own glTF derivation of the retail disc (the private
  per-user cache the Stadiums page builds; 477 stadium scenes = 53 models x 9 variants, scene outer 3136 + stadium
  index, confirmed by the team wall materials: 3137 `falconswall01`, 3139 `billswall`, 3153 = `s17` Louisiana
  Superdome with `roof05`). World centimetres, the same frame as the camera; sidelines at x = +/-2438, goal lines
  z = +/-4572, end lines +/-5486, hashes +/-282, the numbers begin 1097 from the centre line. No retail geometry was
  copied anywhere; only measurements are recorded in the repo.
- Superdome (outer 3153), near side, mid-field: lower bowl `seats4` from the front row (4241, 164) to the back row
  (7029, 1175) with `crowd` cards to 1283; the second level (loge) `seats4` from (5821, 1430) rising to (8711,
  2610), its underside `lambert44` at 1408..1430 from x = 5821, `level_trim` (the loge front trim) at 1430..1962
  from x = 5821, `LIGHT_vip2` corner walls at 970..1467; the third level from x = 5218 at y >= 3321. Beyond the
  goal line the loge corner trim comes in to x = 3779 at 1430..1892 for |z| >= 5080.
- Arizona (outer 3136, the first model): lower bowl x 4008..6812, y 0..1498 (steeper, 28 degrees); the club level
  from x = 5972 at y 1498..2204 with its underside at 1498; the upper deck from 5972 at 2076..3420.
- 16.5 m is exactly the second level's front-row height. With the ball on the near hash (x = +282) the v5.2 eye is
  at x = 5932, 111 cm past the Superdome's loge front (5821) and 40 cm short of Arizona's club front (5972). Any
  ball further toward the camera puts the eye among the second-level seats and crowd cards; a ball at the near
  numbers (x = 1097) puts it 9 m deep into them.
- In the end zones the eye leads the ball by 4.5 m toward the end line, so a ball inside the last 4.5 m of the end
  zone (or a touchdown catch at the end line) puts the eye at |z| >= 5080, inside the loge corner trim's box
  (x >= 3779, y 1430..1892) whenever the offense is moving toward that end zone.

The visible effect was measured with a facing-aware ray caster (Moller-Trumbore in numba, front faces only, the
game's winding: every field-facing seat surface has its cross-product normal toward the field and up, so back faces
are the ones D3D culls) over all 53 models, a 96 x 72 frame at the native 16:9 field of view, the ball on a
17 x 13 grid (x -2400..2400 step 300, z -5400..5400 step 900), both play directions, 23,426 frames. A frame is
"dirty" when more than 2% of its field-of-play pixels are covered by stadium structure nearer than the field
(on-field props such as pylons, yard numbers, benches and dollies excluded). v5.2:

| measure over 53 stadium models | v5.2 |
| --- | --- |
| frames dirty, whole grid | 27.8% |
| frames dirty with the ball between the numbers (|x| <= 1350) | 14.9% |
| frames dirty with the ball between the hashes (|x| <= 600) | 7.8% |
| clean ball.x limit, median over stadiums, mid-field / goal band (3600..4572) / end zone | 1200 / 600 / 0 cm |
| clean ball.x limit, 10th percentile | 300 / 0 / -300 cm |
| stadiums clean only to ball.x <= 300 at mid-field (the near hash) | 15 of 53 |
| what covers the field in the dirty frames (front-face pixels) | crowd 3.4M, seat01 2.5M, concreteA1 1.4M, LIGHT_boxseat01 1.1M, wall06, LIGHT_suite1, lambert44 (loge underside) ... |
| where in the frame (left / middle / right thirds) | 32% / 36% / 32% overall; offense moving +z: 31.5 / 35.6 / 32.9; moving -z: 33.0 / 35.6 / 31.4 |

The Superdome itself: clean at mid-field only to ball.x = 300; with the ball at x = 600 the loge front trim covers
30..70% of the frame at 190..260 cm from the eye; at x = 900 the second-level crowd cards cover 100% of the frame at
11..12 cm. In the end zones the corner trim covers half the frame with the ball on the far hash and all of it from
the centre line on.

On "right side": in the model the intrusion is symmetric to within a few percent. The frame's right edge is world
-z (the projection matrix, calibrated to 0.0002 px against the native projector: right = forward x up). The eye's
2 m lead over the look-at yaws the view 2.2 degrees toward the right for an offense moving toward +z (the direction
in the reporter's frame), which shifts the intrusion slightly right (32.9% vs 31.5%); the Superdome's -z loge
corner trim (screen right) also reaches 1.2 m closer to the field than the +z one (x from 3779 against 4945).
Both are small; the report's "right side" is most likely where his play went. The mechanism is the same on
both sides.

## Root cause at file:line

`mod_editor/core/nfl2k5_camera.py:63` (beta 63): `BROADCAST_VALUES = ((400.0, 0.0, 250.0), 80.0, (5250.0, 1650.0,
200.0))`, the retail TV template's fixed press-box eye reused as the offset of a following (type 2) record. The
template (A881E0, type 0) never moves; a type-2 offset of the same numbers puts the eye 5650 cm toward the camera
side of wherever the ball is, which is inside the stadiums' second level for half of the field, at the exact
height of its front row. No clamp in the descriptor can stop the follow: the solver's eye clamp box
(camera+0x3C0/+0x3D0, `FUN_0005f760` after the type switch) is reset to +/-100000 by every descriptor copy
(`FUN_00060090`) and nothing in retail sets it.

## The fix (numbers only)

`BROADCAST_VALUES = ((400.0, 0.0, 250.0), 68.0, (4500.0, 1400.0, 200.0))`: the mount moves from the press box to the
front of the loge, 45 m toward the camera side and 14 m up (eye = ball + (4900, 1400, 450 x dir)), the lens widened
from 80 to 68 so the framing at the ball is unchanged. Through the native solver (16:9, live state, offense +z),
v5.2 -> v5.3 in 640 x 480 presentation pixels:

| point | v5.2 (x, y) | v5.3 (x, y) |
| --- | --- | --- |
| focus (the ball) | 362, 214 | 361, 215 |
| backfield 7 m | 488, 213 | 484, 213 |
| near wideout | 411, 362 | 421, 370 |
| far wideout | 340, 92 | 337, 101 |
| receiver 15 yd | 87, 182 | 90, 183 |
| far sideline | 338, 111 | 335, 120 |
| near sideline | 418, 451 | 431, 468 |
| 17 yd behind the ball | 640, 211 | 633, 211 |
| 22 yd ahead | -5, 219 | -1, 220 |
| pitch | 17.44 deg | 17.27 deg |
| vertical / 16:9 horizontal field of view | 21.9 / 33.4 deg | 25.6 / 38.9 deg |
| eye to focus | 59.0 m | 51.2 m |

Every sample point is within 10 px of v5.2; the far sideline stays in the top quarter, the near wideout stays
above the scorebug (381), the ball stays centred, the same 17 yards behind to 22 ahead. What changes is
perspective: the camera is 15% closer and 2.5 m lower, so depth reads slightly stronger (a camera at the front of
the loge rather than in the press box; still the last-year TV look). Pitch and framing were kept on purpose: the
alternatives (pull in at 16.5 m: pitch 20.1 deg, the near wideout drops onto the scorebug; lower to 13.5 m at 52.5 m:
pitch 14.4 deg, flatter) either change the accepted look or, over the 53 stadiums, are no cleaner.

Why these numbers, from the survey: the second level's front sits at 5821..5972 in the two dissected stadiums, so
the eye's 4900 cm offset keeps it in front of the loge for every ball up to x = +921 (the near hash is 282, the near
numbers start at 1097); 14 m is under both undersides (1408 Superdome, 1498 Arizona), below the corner trim (1430)
and above the lower bowl's crowd cards until x = 6400..7000 (the survey's mid-field limits: ball.x 1800 in the
Superdome, 1500 in Arizona).
Lower mounts start hitting lower-bowl crowd in the steeper stadiums; higher ones re-enter the second level.

The same survey over all 53 models, v5.2 against v5.3 (and the two variants that were measured and rejected):

| measure | v5.2 | v5.3 (chosen) | 13.5 m at 45 m out | 16.5 m at 45 m out |
| --- | --- | --- | --- | --- |
| frames dirty, whole grid | 27.8% | 18.6% | 20.5% | (not run: changes the look) |
| frames dirty, ball between the numbers | 14.9% | 5.4% | 6.2% | |
| frames dirty, ball between the hashes | 7.8% | 2.3% | 2.8% | |
| clean ball.x limit, median (mid / goal / end zone) | 1200 / 600 / 0 | 1500 / 1200 / 900 | 1200 / 900 / 600 | |
| clean ball.x limit, 10th percentile | 300 / 0 / -300 | 900 / 60 / 0 | 900 / 0 / -300 | |
| worst five (dirty frames between the numbers) | 3177 41%, 3141 39%, 3170 38%, 3146 37%, 3136 34% | 3141 27%, 3146 26%, 3143 22%, 3177 19%, 3142 16% | | |

Per stadium model (clean ball.x limit in cm for the mid-field band |z| <= 3600, the goal band 3600..4572 and the
end zones; 'none' = dirty even with the ball at the far sideline; the dirty share is over the frames with the
ball between the numbers). Stadium names from the team identity table (scene outer = 3136 + stadium index):

| scene outer | stadium (team identity table) | v5.2 clean ball.x mid / goal / end zone (cm) | v5.2 dirty frames between the numbers | v5.3 clean ball.x mid / goal / end zone | v5.3 dirty frames |
| --- | --- | --- | --- | --- | --- |
| 3136 | Arizona Stadium | 300 / 300 / 0 | 34% | 1500 / 1500 / 1500 | 0% |
| 3137 | Georgia Dome | 300 / 300 / 0 | 27% | 1800 / 1800 / 1200 | 0% |
| 3138 | M&T Bank Stadium | 900 / 600 / 600 | 15% | 900 / 900 / 900 | 8% |
| 3139 | Ralph Wilson Stadium | 1200 / 0 / 0 | 10% | 1800 / 300 / 0 | 9% |
| 3140 | B of A Stadium | 1500 / 1500 / 600 | 2% | 1800 / 1800 / 600 | 2% |
| 3141 | Chicago Field | 0 / 0 / -300 | 39% | 300 / 300 / 0 | 27% |
| 3142 | Paul Brown Stadium | 300 / -300 / -300 | 28% | 600 / 0 / -300 | 16% |
| 3143 | Texas Stadium | 300 / 300 / 0 | 34% | 600 / 600 / 600 | 22% |
| 3144 | INVESCO Field | 2100 / 2100 / 1200 | 0% | 2400 / 2100 / 1200 | 0% |
| 3145 | Ford Field | 1200 / 900 / 600 | 2% | 1200 / 1200 / 900 | 1% |
| 3146 | Lambeau Field | 0 / 0 / -300 | 37% | 300 / 300 / 0 | 26% |
| 3147 | RCA Dome | 1200 / 0 / -300 | 11% | 1500 / 0 / 0 | 10% |
| 3148 | ALLTEL Stadium | 1200 / 0 / -300 | 12% | 1500 / 300 / 0 | 9% |
| 3149 | Arrowhead Stadium | 1500 / 600 / 0 | 7% | 1500 / 900 / 0 | 5% |
| 3150 | Pro Player Stadium | 1800 / 1800 / 1800 | 0% | 2100 / 2100 / 2100 | 0% |
| 3151 | H. H. H. Metrodome | 1200 / 1200 / 900 | 1% | 1500 / 1500 / 1200 | 0% |
| 3152 | Gillette Stadium | 1200 / 900 / 600 | 3% | 1200 / 1200 / 900 | 1% |
| 3153 | Louisiana Super Dome | 300 / 300 / -600 | 29% | 1800 / 600 / 0 | 8% |
| 3154 | Giants Stadium | 300 / 600 / 0 | 12% | 1200 / 600 / 300 | 6% |
| 3155 | Jets Stadium | 300 / 600 / 0 | 12% | 1200 / 600 / 300 | 6% |
| 3156 | Network Associates | 1800 / 900 / 300 | 4% | 2100 / 1200 / 600 | 2% |
| 3157 | Lincoln Financial Field | 600 / 600 / 300 | 16% | 900 / 600 / 600 | 7% |
| 3158 | Heinz Field | 900 / 900 / 600 | 5% | 1200 / 900 / 900 | 3% |
| 3159 | Edward Jones Dome | 600 / 600 / 600 | 22% | 2100 / 2100 / 1800 | 0% |
| 3160 | QUALCOMM Stadium | 2100 / 0 / -300 | 6% | 2100 / 0 / -300 | 6% |
| 3161 | San Francisco Park | 1800 / 1800 / 1500 | 0% | 1800 / 1800 / 1500 | 0% |
| 3162 | Qwest Field | 2400 / 2400 / 2400 | 0% | 2400 / 2400 / 2400 | 0% |
| 3163 | Tampa Bay Stadium | 2400 / 2400 / 2400 | 0% | 2400 / 2400 / 2400 | 0% |
| 3164 | Titans Coliseum | 300 / 300 / 300 | 33% | 1200 / 1200 / 1200 | 0% |
| 3165 | Washington Field | 300 / 0 / 0 | 30% | 900 / 600 / 600 | 9% |
| 3166 | Cleveland Stadium | 300 / 0 / 0 | 31% | 900 / 600 / 600 | 10% |
| 3167 | Reliant Stadium | 1200 / 900 / 600 | 3% | 1500 / 1200 / 900 | 1% |
| 3168 | Aloha Stadium | 1200 / 900 / 900 | 3% | 1500 / 1200 / 1200 | 0% |
| 3169 | (not in the team table) | 1200 / 1200 / 900 | 1% | 1500 / 1500 / 1200 | 0% |
| 3170 | (not in the team table) | 0 / 0 / -300 | 38% | 900 / 600 / 300 | 11% |
| 3171 | (not in the team table) | 1200 / 900 / 600 | 3% | 1500 / 1200 / 900 | 1% |
| 3172 | (not in the team table) | 1200 / 0 / -300 | 12% | 1500 / 300 / 0 | 9% |
| 3173 | (not in the team table) | 300 / 300 / 0 | 34% | 1500 / 1500 / 1500 | 0% |
| 3174 | (not in the team table) | 1200 / 900 / 600 | 2% | 1200 / 1200 / 900 | 1% |
| 3175 | (not in the team table) | 1800 / 1800 / 1800 | 0% | 2100 / 2100 / 2100 | 0% |
| 3176 | (not in the team table) | 1200 / 900 / 600 | 2% | 1200 / 1200 / 900 | 1% |
| 3177 | (not in the team table) | 300 / -300 / -1800 | 41% | 900 / 300 / -900 | 19% |
| 3178 | ESPN Stadium | 600 / 300 / 300 | 18% | 900 / 600 / 600 | 7% |
| 3179 | Cheesesteak Dome | 1200 / 0 / -300 | 11% | 1500 / 0 / 0 | 10% |
| 3180 | Loco Arena | 1200 / 0 / -300 | 11% | 1500 / 0 / 0 | 10% |
| 3181 | Electra Coliseum | 1200 / 1200 / 900 | 1% | 1500 / 1500 / 1200 | 0% |
| 3182 | Funk Field | 300 / 300 / -600 | 29% | 1800 / 600 / 0 | 8% |
| 3183 | Dream Superdome | 600 / 600 / 600 | 22% | 2100 / 2100 / 1800 | 0% |
| 3184 | Alien Arena | 300 / 300 / 0 | 27% | 1800 / 1800 / 1200 | 0% |
| 3185 | (not in the team table) | 300 / 300 / 0 | 27% | 1800 / 1800 / 1200 | 0% |
| 3186 | (not in the team table) | 1200 / 0 / -300 | 11% | 1500 / 0 / 0 | 10% |
| 3187 | (not in the team table) | 1200 / 1200 / 900 | 1% | 1500 / 1500 / 1200 | 0% |
| 3188 | (not in the team table) | 300 / 300 / -600 | 29% | 1800 / 600 / 0 | 8% |

The mount's z lead was measured too: keeping the eye 4.5 m ahead of the ball (the template's 200 plus the 250
look-at lead, kept), or 2.5 m ahead (offset z 0), or level with the ball (offset z -250) changes the whole-grid
dirty share by 0.1% and the between-the-numbers share from 5.4% to 5.3% and 5.1%; only the goal band's 10th
percentile moves (60, 300, 600 cm). Not worth changing the accepted perspective on the line of scrimmage, so
the template's z stays; the corner residual is part of what the WIRING.md callback fixes.

What remains, honestly: a constant-offset type-2 mount follows the ball across the field, so plays wider than about
9 m past the centre line toward the camera still carry it into the seats of the stadiums whose second level is
low or close (Chicago Field 3141: loge front at x = 5296 with the underside at 1103; Lambeau Field 3146; Texas
Stadium 3143). The complete fix is one owned setup callback that sets the solver's eye clamp box (max x 5600, optionally z within
+/-5500) so the mount pans instead of dollying into the stands; that is new code and a grown request, described
in `WIRING.md` for a later beta, not a hotfix. The retail director's own type-1 record (fixed world eye with the native
auto-zoom: lens = distance x K / framing word, `FUN_0005e190`) is the other structural option and a different look.

## What changed (files)

- `mod_editor/core/nfl2k5_camera.py`: `BROADCAST_VALUES` lens 80 -> 68, offset (5250, 1650, 200) -> (4500, 1400,
  200); comments and the descriptor docstring. Descriptor: 80 owned RO bytes at the same address, now differing from
  the retail template in type, look-at, lens and the mount's x and y (+48, +52); the 160 RX wrappers, hooks, pins,
  requests and reservations are unchanged. `status()`/`apply()` idempotent as before (the broadcast test's
  integrity cases cover the forged-descriptor refusals and the v4-size refusal).
- `tools/nfl2k5_camera_broadcast_proof.py`: the near-side stands model (`STANDS`: the second level's front and
  underside, the Superdome's lower bowl and crowd cards, the loge corner trim), the sampled ball grid (12 x 25
  positions: x from the far sideline to `CLEAN_BALL_X` = 900 toward the camera in 300 cm steps, z the whole field
  including both end zones in 457 cm steps), `stands_violations()` and, per projection row, the violations of the
  settled native eye; a `stands` summary in the evidence (the v5.2 eye's 95 violations per direction on the same
  grid, the fix's 0). `revision` recorded in the JSON.
- `tests/mod_editor/test_nfl2k5_camera_broadcast.py`: the regression test
  `test_mount_stays_clear_of_the_near_stands_for_every_sampled_ball_position` (red with the v5.2 numbers, 95
  violations per row: the second level from ball.x = 300, the corner trim in the end zones; green with v5.3), one
  shared native projection run for both proofs, and the descriptor pin `[0, 16, 24, 32, 48, 52]`.
- `docs/mod_editor/nfl2k5_camera_broadcast_proof.v5.json` and `..._projection.v5.png` regenerated (156 cases).
- `mod_editor/core/providers.py`: the camera source pin (`packaging/repin.py --apply`).
- `docs/mod_editor/2k5_mod_studio_changelog.md` (a "Beta 63.1 hotfix" section, one entry), `BETA_RELEASE_NOTES.md`
  (one sentence on the Broadcast row), `WIRING.md` (the section on top: manifest regeneration now; the eye-clamp
  callback as the described complete fix).

No protected file was edited. Retail inputs were read in place (`/media/noah/Storage/for codex 1.0/...`, and the
Stadium Studio's private derived cache under `~/.cache/2k5-mod-studio/`), never copied.

## Manifest: Claude must regenerate

`mod_editor/core/nfl2k5_camera.py` is a pinned writer source and changed. `data/nfl2k5_cave_reservations.json`
(manifest 29) carries its beta-63 fingerprint; the cave oracle suite's two manifest-loading cases error with
`OracleError: stale reservation source: mod_editor/core/nfl2k5_camera.py; regenerate manifest` (27 of its 29 tests
pass; output below) until the manifest is regenerated. The reserved spans, sizes and allocator requests did not
change, so both XBE gates were run against manifest 29 as it is (both green, results below). A scratch manifest
observed from the current sources by the Guardian observer makes the whole oracle suite green (29, one
resource-only skip), so the production regeneration should be routine.

## Tests and commands

All run from the worktree with `PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/<file>.py`
(plain unittest, standalone, as CI does).

| file | tests | result | seconds | wall | peak KiB |
| --- | ---: | --- | ---: | --- | ---: |
| `tests/mod_editor/test_nfl2k5_camera_broadcast.py` | 9 | OK | 41.204 | (no /usr/bin/time on this run) | |
| `tests/mod_editor/test_nfl2k5_camera_far.py` | 16 | OK | 108.043 | 1:48.53 | 801,792 |
| `tests/mod_editor/test_nfl2k5_widescreen_polish.py` | 13 | OK | 7.835 | 0:08.03 | 324,932 |
| `tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -k camera_v5` | 24 | OK | 253.450 | 4:13.74 | 135,248 |
| `tests/mod_editor/test_camera_inspection.py` | 17 | OK | 0.005 | 0:00.12 | 28,928 |
| `tests/mod_editor/test_xbe_patch_memory_writes.py (gate)` | 111 | OK | 1208.044 | 20:08.34 | 329,448 |
| `tests/mod_editor/test_xbe_patch_cave_references.py (gate)` | 123 | OK | 1377.780 | 22:58.28 | 518,976 |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py (expected to refuse the stale pinned source until the manifest is regenerated)` | 29 | FAILED (errors=2) | 277.942 | 4:43.37 | 915,788 |
| `tests/mod_editor/test_nfl2k5_guardian_manifest.py` with `NFL2K5_GUARDIAN_MANIFEST_OUTPUT=<scratch>/observed-xbe-manifest.json` (the observer regenerates an XBE-only manifest from the current sources) | 1 | OK | 235.760 | 3:56.05 | 240,480 |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` with `NFL2K5_CAVE_MANIFEST=<scratch>/observed-xbe-manifest.json` | 29 | OK (skipped=1: the resource-only case skips for an XBE-only manifest, as in the v5 delivery) | 272.110 | 4:36.76 | 931,844 |

`python3 tests/mod_editor/test_nfl2k5_camera_broadcast.py` (v5.3, 9 tests; the new regression test included):

```text
.........
----------------------------------------------------------------------
Ran 9 tests in 41.204s

OK
```

The same regression test against the v5.2 numbers (`BROADCAST_VALUES` patched back to `((400, 0, 250), 80, (5250, 1650, 200))` before the run), red as required:

```text
    self.assertEqual(row['stands']['violations'], [], (row['aspect'], row['direction'], row['state'], row['pass_zoom']))
AssertionError: Lists differ: [{'kind': 'corner trim', 'ball': (-1800.0,[9480 chars]: 1}] != []

First list contains 95 additional elements.
First extra element 0:
{'kind': 'corner trim', 'ball': (-1800.0, 5025.0), 'eye': (3850.0, 1650.0, 5475.0), 'direction': 1}

Diff is 10957 characters long. Set self.maxDiff to None to see it. : ('4:3', 1, 1, 0)

----------------------------------------------------------------------
Ran 1 test in 17.113s

FAILED (failures=1)
RED as expected
```

`python3 tools/nfl2k5_camera_broadcast_proof.py --json docs/mod_editor/nfl2k5_camera_broadcast_proof.v5.json --png docs/mod_editor/nfl2k5_camera_broadcast_projection.v5.png`:

```text
156 bounded native projection cases; EXPERIMENTAL / UNWITNESSED
	Elapsed (wall clock) time (h:mm:ss or m:ss): 0:22.15
	Maximum resident set size (kbytes): 284852
```

`python3 packaging/repin.py --apply`:

```text
$ python3 packaging/repin.py --apply
[1] mod_editor/core/providers.py: mod_editor/core/nfl2k5_camera.py
    968257d009fbdd0d47f1dfa44b781d788cf0202ae46ddc83337190f14c9feaa2
 -> 9cb36a9769105cdee8d361563131989ca970f658ff142cba670cfce1bd014c23

applied 1 pin update(s)
```

`python3 tests/mod_editor/test_xbe_patch_memory_writes.py`:

```text
Ran 111 tests in 1208.044s
OK
	Elapsed (wall clock) time (h:mm:ss or m:ss): 20:08.34
	Maximum resident set size (kbytes): 329448
```

`python3 tests/mod_editor/test_xbe_patch_cave_references.py`:

```text
Ran 123 tests in 1377.780s
OK
	Elapsed (wall clock) time (h:mm:ss or m:ss): 22:58.28
	Maximum resident set size (kbytes): 518976
```

`python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` (manifest 29 pins the beta-63 camera source; Claude regenerates):

```text
ERROR: test_release_manifest_includes_resource_build_steps (__main__.CaveOracleTests.test_release_manifest_includes_resource_build_steps)
mod_editor.core.nfl2k5_cave_oracle.OracleError: stale reservation source: mod_editor/core/nfl2k5_camera.py; regenerate manifest
ERROR: test_retail_current_stack_owns_every_supplied_cave_and_runtime_flag (__main__.CaveOracleTests.test_retail_current_stack_owns_every_supplied_cave_and_runtime_flag)
mod_editor.core.nfl2k5_cave_oracle.OracleError: stale reservation source: mod_editor/core/nfl2k5_camera.py; regenerate manifest
Ran 29 tests in 277.942s
FAILED (errors=2)
	Elapsed (wall clock) time (h:mm:ss or m:ss): 4:43.37
	Maximum resident set size (kbytes): 915788
```

`NFL2K5_GUARDIAN_MANIFEST_OUTPUT=<scratch>/observed-xbe-manifest.json python3 tests/mod_editor/test_nfl2k5_guardian_manifest.py` (the scratch observed manifest, never the production JSON) and then `NFL2K5_CAVE_MANIFEST=<scratch>/observed-xbe-manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py`, the same suite green once a manifest observed from the current sources is supplied:

```text
Ran 1 test in 235.760s
OK
	Elapsed (wall clock) time (h:mm:ss or m:ss): 3:56.05
	Maximum resident set size (kbytes): 240480
```

```text
Ran 29 tests in 272.110s
OK (skipped=1)
	Elapsed (wall clock) time (h:mm:ss or m:ss): 4:36.76
	Maximum resident set size (kbytes): 931844
```

`python3 tests/mod_editor/test_nfl2k5_camera_far.py`:

```text
Ran 16 tests in 108.043s
OK
	Elapsed (wall clock) time (h:mm:ss or m:ss): 1:48.53
	Maximum resident set size (kbytes): 801792
```

`python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -k camera_v5`:

```text
Ran 24 tests in 253.450s
OK
	Elapsed (wall clock) time (h:mm:ss or m:ss): 4:13.74
	Maximum resident set size (kbytes): 135248
```

`python3 tests/mod_editor/test_nfl2k5_widescreen_polish.py` and `test_camera_inspection.py`:

```text
Ran 13 tests in 7.835s
OK
	Elapsed (wall clock) time (h:mm:ss or m:ss): 0:08.03
	Maximum resident set size (kbytes): 324932
Ran 17 tests in 0.005s
OK
	Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.12
	Maximum resident set size (kbytes): 28928
```


## What Noah must witness in xemu

1. Options > Camera > Broadcast on a beta 63.1 disc: the same shot as beta 63 (the ball centred, about 17 yards
   behind to 22 ahead at 16:9, far sideline in the top quarter, the near wideout above the scorebug) but from a
   camera a little closer and lower, at the front of the loge. Say if the perspective feels wrong; pitch and framing
   at the ball are v5.2's.
2. The report itself: plays at the near hash and runs toward the near sideline in the Superdome (WAS at NO as in
   his frame) and at Arizona, Atlanta, Baltimore. Up to about 10 yards past the centre line toward the camera there
   must be no crowd or structure over the field; past that, into the near numbers and the sideline, some stadiums
   (Chicago Field, Lambeau Field, Texas Stadium first) will still show seats or crowd at the frame's edge: that is the residual
   the numbers cannot remove and the WIRING.md callback would.
3. End-zone plays with the offense driving toward the camera's right (world -z) and left: the loge corner trim
   should no longer fill the frame on touchdown catches near the end line.
4. Kickoffs, punts and the kick-flight state still use the same record (the look-at height cap keeps the eye
   from rising with the ball); check the return framing did not change character.
5. Both play directions, 4:3 and 16:9; the Broadcast row still starts after Custom, Standard still starts every
   game (unchanged by this hotfix).

ASTRA_DONE
