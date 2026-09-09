# Hotfix beta-63.1: imported shoe textures reach the game, not just Edit Player

Branch `astra/hf63-shoes` from tag `beta-63` (9c17c538). Bug: maumau78, #2k5-bugs
2026-09-09 05:26 / 06:09, beta 63 in xemu: "I can import shoe texture and editor
show them; in-game they load default texture" (screenshot `2k5-bugs_006.png`: the
EDIT PLAYER screen, Right Shoe Style 1, orange imported shoe on the preview
model; stock shoes in the game).

Everything below is proved offline on the pinned retail executable and the
retail pack index (read-only, never copied). No emulator was run; nothing
in-game is witnessed by me. `ASTRA_DONE` is the last line.

## 1. Reproduction

The Studio's shoe import (`facade.replace_equipment_texture` ->
`nfl2k5_equipment_import.stage_equipment_import`) staged exactly one asset:
the selected package's `tset:<outer>:8:0:shoes01`. Behavioural red run on the
pre-fix tree (the new session test against the old facade):

```
AssertionError: Tuples differ: ('tset:0:8:0:shoes01',) != ('tset:0:8:0:shoes01', 'tset:1:8:0:shoes01', 'tset:2:8:0:shoes01')
FAILED (failures=1)
```

One package changed; the game does not read that package for Style 1 in a
game (section 2), so the import could only ever show on the Edit Player model.

## 2. Consumer chain proof (retail `default.xbe`, SHA-256 73105b17...a4a9)

Player shoe materials `SHOE_L` / `SHOE_R` / `SHOE_both` / `SHOE_tapes`
(`SHOE_spikes` on hi_body) live in the shared player scenes `lo_body`
(outer 3 chunk 113) and `hi_body` (outer 3 chunk 114) with unmapped texture
pointers; the binder fills them at runtime. The chain, function by function
(virtual addresses; every range is hash-pinned in
`tests/mod_editor/test_nfl2k5_equipment_consumers.py::XBE_EVIDENCE`):

| Step | Address | What it does |
| --- | --- | --- |
| Shoe style bits | `FUN_0008EFA0` tail, `0x0008F74A..0x0008F7E3` | player record byte `+0x0C`: bits 0-2 and 3-5 are the two shoe styles (0..5, 6 = taped). Equal -> `SHOE_both` (slot 0x3B); different -> `SHOE_R` (0x3A) / `SHOE_L` (0x39); any 6 -> `SHOE_tapes` (0x3C) with style 6. Slot 0x3D `SHOE_spikes` is filled too when `FUN_00077460()+0x1C` is set. Material-slot names are the 62-entry table at `0x004EEE68` (`0x39 SHOE_L`, `0x3A SHOE_R`, `0x3B SHOE_both`, `0x3C SHOE_tapes`, `0x3D SHOE_spikes`). |
| Style -> cache row | `FUN_0008EF20` (`0x0008EF20`, 115 B) with the shoe table at `0x004EF7C0` (8 B per style) | style 0..6 -> cache rows 84 `shoes01`, 85 `shoes04`, 86 `shoes09`, 87 `shoes02`, 88 `shoes03`, 89 `shoes10`, 90 `shoes_taped`; second word = bump map index (`bump_shoes1..7`). Edit Player "Style 1" is `shoes01`, "Style 2" `shoes04`, "Style 3" `shoes09`, "Style 4" `shoes02`, "Style 5" `shoes03`, "Style 6" `shoes10`. Texture = `DAT_00B65428[(mud*2 + side)*96 + row]`, written into the material at `+0x30` by `FUN_0008E3F0` (`0x0008E422`). |
| Cache fill | `FUN_0008E620` (`0x0008E620`, 368 B) | walks the 96-row binding table at `0x004EEAF8` (name pointer, context-first word) for clean/mud x HOME/AWAY through `FUN_0008E5C0` (adds `_mud`) and `FUN_0008E580`. |
| The decision | `FUN_0008E580` (`0x0008E580`, 49 B): `85 C0 74 1A` = `TEST EAX,EAX / JZ global` | context-first word 1: `FUN_000449E0(HOME or AWAY name, 'TXTR', name)` first, global fallback. Word 0: `XOR ECX,ECX; JMP FUN_000449E0` = global lookup only, the team's package is never consulted. |
| Global lookup | `FUN_000449E0` (`0x000449E0`, 104 B) | `ECX == 0`: walk the context list from `DAT_00B09578` (`MOV ESI,[0xB09578]` at `0x00044A19`, `MOV ESI,[ESI]` next) and return the first context whose resource list has a `TXTR` of that name. |
| List order | `FUN_00043DB0` (`0x00043DB0`, 82 B) | every new context is inserted at the head (`MOV [ESI],old_head; ...; MOV [0xB09578],ESI` at `0x00043DE0`). Newest context wins the walk. |
| Game load order | `FUN_00062BE0`, `0x00063261..0x000632A3` | `STADIUM`, then `HOME` (`MOV ECX,0xE6162C 'HOME'` at `0x00063275`, filename buffer `0xB30710` = `<code>h<style>.iff`), then `AWAY` (`0x00063293`, buffer `0xB30730` = `<code>a<style>.iff`). AWAY is created last, so it is the newest uniform context. |
| Front-end preview | `FUN_00091940` (`0x00091940`, 248 B) | loads ONE package into `DAT_00B651A0`: `%sh0.iff` under `HOME` (or `%sa0.iff` under `AWAY` when `FUN_000EC060` and player side byte `+0x34 == 2`), `36h0`/`36a0` for a player without a team. |

Binding-table rows (`0x004EEAF8 + row*8`, pinned 768 B):

| Row | Name | context-first | Where the game reads it |
| ---: | --- | ---: | --- |
| 84 / 85 / 87 / 88 | `shoes01` / `shoes04` / `shoes02` / `shoes03` (Styles 1, 2, 4, 5) | 0 | the newest loaded uniform package |
| 86 / 89 | `shoes09` / `shoes10` (Styles 3, 6) | 1 | the player's own HOME/AWAY package |
| 90 | `shoes_taped` | 0 | outer 3 (global pack) |
| 27-30 / 31-34 | `glove01-04` / `glove05-08` | 0 / 1 | newest package / own package |
| 35, 36 / 37 | `longsleeve01, 02` / `longsleeve03` | 0 / 1 | newest package / own package |
| 68-71 / 72-74 | `elbowpad01-04` / `elbowpad05-07` | 0 / 1 | newest package / own package |
| 78, 79 / 83 | `wristband01, 02` / `wristband09` | 0 / 1 | newest package / own package |
| 91 | `socks00` | 1 | own package |

Only the 634 uniform packages carry `shoes01..04`, `glove01..04`,
`elbowpad01..04`, `longsleeve01..02`, `wristband01..02` (all TSET chunks
4-10; the global pack outer 3 has `shoes_taped`, `elbowpad_rubber/elastic/
taped`, `wristband_qb`, `bump_shoes1..7` and no `shoes0N`; checked against
`reports/assets/nfl2k5_resource_chunks_v2.json` and a decode of outer 3 / 346
TSETs). Therefore:

* **In a game** every player on both teams wearing Style 1/2/4/5 samples the
  AWAY package's copy (`<away code>a<style>.iff`, chunk 8/9). The HOME
  package's copy is never sampled for those rows.
* **On the Edit Player screen** the preview samples the viewed team's `h0`
  (or `a0`) package because it is the only uniform package loaded.
* That is exactly maumau78's screen: he edited a home package (the preview
  model's `h0`), so the preview showed the orange shoe and the game (reading
  the opponent's `a<style>` package, or his own `a` package when away) did not.
* Style 3 (`shoes09`) and Style 6 (`shoes10`) really are per package; imports
  of those were already correct.

The retail art is not identical across packages (chunk 8 has 66 distinct
retail spans across 634 packages; `shoes01` has 66 distinct pixel/palette
combinations), so "whichever package loaded last" is a real visible rule, not
a harmless one.

## 3. Root cause (file:line, pre-fix tree)

`mod_editor/core/nfl2k5_equipment_import.py:57-62` staged the import as
`session.replace_batch(((asset, staged),))`: one replacement entry for the
selected `tset:<outer>:<chunk>:<ref>:<name>` only. The writer
(`nfl2k5_uniform_equipment_writer.py`) and the catalog model every equipment
texture as package-local, which is true for the context-first rows and false
for the global rows the game reads from the newest package. No component knew
which package the game samples.

## 4. The fix

No protected file was edited; no `WIRING.md` change is needed.

1. `mod_editor/core/nfl2k5_uniform_equipment_writer.py`
   * `BINDING_TABLE_ROWS`, `GLOBAL_LOOKUP_NAMES`, `CONTEXT_FIRST_NAMES`,
     `SHOE_STYLE_NAMES`: the binding table knowledge above, documented at the
     top of the module with the addresses.
   * `in_game_lookup(name)`, `sampled_package(selector)`,
     `consumer_targets(target, by_id)`: a context-first name resolves to the
     selected package; a global name resolves to the selected package plus
     every package the game can bind it from: all 317 `<code>A<style>`
     packages (any of them can be the AWAY context) and the 85 `<code>H0`
     packages (the only packages the front-end preview loads). Other home
     styles are never the newest uniform context anywhere, so they are not
     staged unless selected.
   * `EquipmentCompileCache` + `compile_cache=` on
     `build_unified_uniform_equipment_imports`: the compile is split into a
     per-span core (`_compile_group`, keyed by template span SHA-256, chunk
     header, catalog rows and the authored RGBA/mode/scale) and a per-package
     envelope (asset IDs, set selector, preview names, pack offset, hashes).
     Identical retail spans receiving identical artwork compile once; the
     output bytes and receipts are identical to the uncached path. Nothing is
     cached without an explicit cache object (tests that patch the compressor
     keep failing the way they expect).
   * `_rebuild_fixed_span`: a palette-only edit still uses the retail greedy
     transport first (byte-identical spans and receipts for everything that
     fit before). When that overflows, it takes the bounded lossless route the
     own-texture import already uses (retail-observed 10/11/12/13-bit
     geometries, minimum-bit-cost token parse, full decode-and-compare). This
     was needed by the fan-out itself: Tennessee `17H0` chunk 8 (55,776 stored
     / 55,772 consumed, 13-bit distances, byte-identical in 91 packages) has
     its sibling palettes matched against `shoes01`'s, so replacing that one
     palette grows the greedy stream by 19-246 bytes whatever the palette
     budget ("cannot fit ... even with a two-colour palette" from the first
     real build). The optimal parse fits it with 513 bytes to spare at the
     full 34-colour budget.
   * Pack-extent guard: three packages straddle two pack files (`01H11`
     outer 3625, `25H3` 3832, `24A10` 4136). The writer used to refuse the
     whole package; it now refuses only a span that crosses the seam and
     writes a span that lies inside one extent at its real pack offset
     (`24A10` chunk 8 -> pack `B` offset 457,930,128, bytes verified against
     the template hash). `24A10` is an away package and therefore a sampled
     copy; every sampled copy of every global row lies inside one extent
     (retail-gated test).
2. `mod_editor/core/nfl2k5_equipment_import.py`
   * `stage_equipment_import` resolves the consumer set, keeps the existing
     preflight (the selected package's TSET with its staged siblings), and
     stages one `replace_batch` with the selected frozen PNG plus, for every
     other consumer package, a canonical re-encode of the same decoded pixels
     carrying its own explicit texture choice (`npTC` intent names the copy's
     asset ID). One undo action. Importing the original pixels restores every
     staged copy. The receipt gains `consumers` (schema
     `nfl2k5_equipment_consumer_fanout/v1`: lookup kind, the rule, the XBE
     evidence, package counts, every consumer and staged asset ID). The
     message says where it went, e.g. "In a game every player wearing this
     style uses the away team's package copy, so it was staged into all 402
     uniform packages (317 away, 85 home Current Uniform)."
   * `revert_equipment_import(session, asset)`: reverts every staged copy of
     the variant as one undoable transaction.
   * `EquipmentImportResult.consumer_asset_ids` (new, defaulted).
3. `mod_editor/studio/facade.py::revert_asset`: equipment assets revert
   through the consumer set ("Reverted X and the same texture in 401 other
   uniform packages.").
4. `mod_editor/core/nfl2k5_extended_visual_io.py::_decode_uniform_equipment`:
   a bounded per-session cache keyed by the retail span hash (decode each
   distinct span once). First import of a global variant fell from 82 s to
   34 s on the real catalog; a repeat import is 5 s; save 0.7 s, load 1.3 s,
   revert 1.7 s.
5. `tools/nfl2k5_visual_mod_project.py`: one `EquipmentCompileCache` per
   build passed to every equipment group.
6. `docs/mod_editor/2k5_mod_studio_getting_started.md`: the rule, in plain
   words, under the 45-equipment-texture paragraph.
7. `tests/mod_editor/test_nfl2k5_equipment_texture_chain.py`: the synthetic
   fixture accepts explicit names and its segments carry a size.
8. Pins: `python3 packaging/repin.py --apply` updated 5 pins
   (`providers.py` x4 for the writer, the visual IO, the visual project
   backend; `check_2k5_mod_studio_runtime.py` for the facade). Claude:
   the cave reservation manifest does not change (no executable writer was
   touched), but the provider/runtime pins did, so regenerate whatever
   release-side manifest lists those hashes.

What the fix does not do: it does not change the executable. A 14-dword
`.rdata` flip of the context-first words at `0x004EEAF8 + row*8 + 4` for the
global rows would make every generic variant team-specific (and make the
Edit Player preview and the game agree per team), but it changes retail
rendering for untouched packages, conflicts with the hi-res pack's pinned
`(0x004EEAF8, 768)` consumer range, and needs BuildPlan wiring in the
protected `mod_build.py`. That is a feature decision for Noah, not a hotfix;
the offsets are recorded here if he wants it.

Costs, measured on the real packs: staging Style 1 shoes for one team creates
402 replacement entries (the same 26 KB canonical PNG each for flat art; a
photo-like shoe would be ~100 KB each, so up to ~40 MB per style in a
project); a build compiles 66 distinct spans and reuses them for the other
336 packages (238 s for the 402 groups in a standalone measurement, one of
them through the optimal parse).

## 5. Tests

All run from the worktree root with `PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/<file>.py`
(the three older suites below add `:$PWD/tools`, as they always did).

Regression test (red before, section 1; green after):

```
$ python3 tests/mod_editor/test_nfl2k5_equipment_consumers.py
.................
----------------------------------------------------------------------
Ran 17 tests in 13.937s

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

The 17 tests: retail-gated (`default.xbe`) pins of every evidence range,
row-by-row classification of the 96-row table against
`BINDING_TABLE_ROWS`/`GLOBAL_LOOKUP_NAMES`, the shoe style table, the
`TEST/JZ`, `XOR ECX,ECX`, head-insert and HOME/AWAY/`%sh0.iff` bytes;
catalog-only consumer resolution (402 = 317 away + 85 H0 for every global
name incl. `_mud`, 403 when an alternate home package is selected, 1 for every
context-first name); a synthetic four-package archive through the real
`StudioSession` + facade (fan-out, alternate home package, team-specific
variant, own-texture intent per copy, restore + revert + undo, repeat import
no-op, second style); the compile cache (hit/miss, identical bytes, per-package
envelope); retail-gated (pack index) shared-span reuse with reparse of every
output, the `17H0` tight-slot fallback with reparse and both loader guards, and
the straddling-package extent proof.

Suites touching the changed modules:

```
test_nfl2k5_equipment_import: OK            (11 tests)
test_nfl2k5_equipment_texture_chain: OK     (16 tests)
test_nfl2k5_equipment_import_wiring: OK     (6 tests)
test_player_assets: OK
test_uniform_sharing: OK
test_2k5_uniform_equipment_export: OK (skipped=4)
test_nfl2k5_extended_visuals: OK
test_studio_session: OK
test_team_kit_product_integration: OK
test_all_texture_lane: OK (skipped=13)
test_provider_integrity: OK
test_providers: OK
test_phase1_packaging: OK
test_stage_release: staged 2 files; 0 declared inputs absent
```

XBE gates `test_xbe_patch_memory_writes.py` / `test_xbe_patch_cave_references.py`:
not run; no executable writer or cave was touched (resource data only).

Real-session proof (scratch harness, retail index read-only, real catalogs):

```
asset: Shoes 01 — Tennessee Titans Home uniform_equipment_texture 256 256
stage: 34.1 s; changed=402 modified=True
message: Equipment recolour is ready to build. In a game every player wearing this style uses the away team's package copy, so it was staged into all 402 uniform packages (317 away, 85 home Current Uniform).
consumers: global {'away': 317, 'home_current': 85, 'selected_only': 0} 402
edits staged: 402
save: 0.7 s size=0.2 MB
load: 1.3 s edits=402
repeat: 5.3 s changed=0
revert: 1.7 s reverted=402 left=0
undo restores: 402
```

Real build of that 402-edit project with `tools/nfl2k5_visual_mod_project.py build`
(retail XISO as source, output in scratch, deleted afterwards):

```
NFL2K5_VISUAL_MOD_BUILD_PASS edits=402 changed=6422383 sha256=9c9e0677235c2af6b949bb4c3625d8d4e50c724481e29650bf1a57d85afc3d69 runtime=false
real 5m6.104s   user 4m21.481s   sys 0m28.810s
```

Manifest: 402 non-overlapping spans (22,204,032 selected bytes, 6,422,383
changed), every byte outside the spans identical, targets in packs `9` (2),
`A` (24), `B` (266) and `C` (110); 311 spans through the retail greedy
transport, 91 (the `17H0` family) through the optimal parse, all 402 at the
full 256-colour budget (34 palette entries). Spans re-read from the output
image and decoded: `24A10` (`4136:8`, pack B, 12-bit, 54,670/54,944), `17H0`
(`3753:8`, 13-bit, 55,263/55,776), `28H0` (`3850:8`, 12-bit, 54,453/54,688),
each matching its manifest hash. The first build attempt, before the
lossless fallback and the extent fix, refused with "cannot fit inside the
retail 55,776-byte TSET even with a two-colour palette" and "package crosses
pack extents and is read-only"; both are covered by the retail-gated tests
now.

## 6. What Noah must witness in xemu

1. Load the retail disc, pick any team, import a clearly different Style 1
   shoe (`Shoes 01`) for that team's home Current Uniform. The message must
   say 402 packages. Build.
2. Edit Player for that team: Right/Left Shoe Style 1 shows the design on the
   preview (as before). Edit Player for another team: the preview also shows
   it (that is the game reading the same league-wide row).
3. Play a game as that team at home and as the away team: every player on
   both sides with Style 1 shoes wears the design; Styles 3 and 6
   (`shoes09`/`shoes10`) stay stock. This is the claim the fix makes and
   nothing offline can show it.
4. Set a player to Style 2 (`shoes04`) and Style 4 (`shoes02`) without
   importing them: stock. Import a `Shoes 04`: same fan-out, same check.
5. Revert the shoe from any package in All Textures: the message says 401
   others were reverted; rebuild shows stock shoes.
6. Try a team whose away package has the tight `17H0`-family span (Tennessee
   current home is one; the receipt names `optimal_token_parse` for those
   91 packages) and confirm the shoes load and look right close up and at
   distance, since that transport is new for palette-only edits.
7. A muddy game (`_mud` rows follow the same rule): the dirty shoe stays
   stock unless `Shoes 01 — Mud` was imported too.

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

# beta-63.1: catch-slider interception scaling no longer applies to kick returners

Implemented on `astra/hf63-catch-slider-kicks`, based on beta-63
`9c17c538847c4fc7511f127bae538f2c6bb5874a`. No push, xemu, GUI display, or audio.
Retail inputs were read only; no retail executable/disc fixture is committed.

## Reproduction and root cause

Read `ASTRA_BRIEF.md`, `HOTFIX_CONTEXT.md`, the supplied verification report's
“Separate interception-slider diagnostic,” and its probe/results. Added a
standalone regression before changing the writer:

```sh
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_catch_slider_kicks.py -v
```

It enters retail `0x1C8312`, executes the installed `0x1C8317` RNG hook and
retail comparison, and stops at the native catch (`0x1C832F`) or deflect
(`0x1C834C`) branch. Only RNG is substituted. Inputs are explicitly supplied:
probability 1, no veto, opposite-team CPU catcher, both Catching factors 50,
ball kind 3 or 4, phases 2/4, and draws 0/0.05/0.5/0.99. `.text` is protected
read/execute during execution. These are deterministic decision counts, not
gameplay catch rates, approach/contact simulation, or an in-game reproduction.

Before the fix, the kick regression failed with this table. Each cell is
four draws times two phases:

| Installed patches | INT 0 | INT 25 | INT 50 | INT 100 |
| --- | ---: | ---: | ---: | ---: |
| Retail | 8/8 | 8/8 | 8/8 | 8/8 |
| Dynamic kickoff only | 8/8 | 8/8 | 8/8 | 8/8 |
| Catch-slider only | 0/8 | 4/8 | 8/8 | 8/8 |
| Dynamic kickoff + catch-slider | 0/8 | 4/8 | 8/8 | 8/8 |

Red output tail (`.scratch/hf63-catch-slider-red-fast.log`):

```text
kind=3 catch_slider_only: 0/8 | 4/8 | 8/8 | 8/8
kind=3 dynamic_and_catch_slider: 0/8 | 4/8 | 8/8 | 8/8
FAIL: test_kicked_ball_ignores_interception_at_native_boundary
Ran 2 tests in 9.813s
FAILED (failures=1)
```

Root cause: beta-63 `mod_editor/core/nfl2k5_catch_slider.py:92-115` uses only
`[catcher+0x38] != [0xE60280]` to classify a defender. A returner before the
possession swap satisfies that predicate. The cave returns
`rand / (2 * Interception)` without the native forward-pass guard. At INT 0,
positive draws become infinity and draw 0 becomes unordered; the native
comparison rejects both even against supplied probability 1. This establishes
a cause for the reported symptom when that slider is lowered; the reporter's
actual setting and a complete live-play reproduction remain unobserved.

## Retail instruction proof of the discriminator

The field is the dword at **`0xE602C0`**. Kind **4** is a forward pass;
kind **3** is a non-forward loose ball, including kicks and backward passes.
It is not an exclusive “kickoff” enum. The implementation uses equality to 3,
so kinds other than 3 keep their previous cave behavior. A phase-only test
would be wrong because punts and forward passes both occur in phase 4.

Instruction evidence from the read-only retail XBE:

```text
00222D01  E8 9A AF EB FF                 call 000DDCA0  ; kick launch release
000DDCCB  E9 40 2C FC FF                 jmp  000A0910
000A092D  E8 BE 77 01 00                 call 000B80F0
000B8110  A1 C0 02 E6 00                mov eax,[00E602C0]
000B8115  83 E8 02                      sub eax,2
000B8118  75 2D                         jne 000B8147   ; keep a forward pass (4)
000B811F  A1 B8 02 E6 00                mov eax,[00E602B8]
000B8124  83 F8 0E                      cmp eax,14
000B8127  74 14                         je 000B813D
000B813D  C7 05 C0 02 E6 00 03 00 00 00 mov [00E602C0],3

000B7410  C7 05 C0 02 E6 00 03 00 00 00 mov [00E602C0],3 ; kick/loose-ball setter
000B6705  C7 05 C0 02 E6 00 04 00 00 00 mov [00E602C0],4 ; forward-pass setter
000B6745  C7 05 C0 02 E6 00 03 00 00 00 mov [00E602C0],3 ; backward-pass setter

001C807D  83 3D C0 02 E6 00 04          cmp [00E602C0],4
001C8084  0F 85 AD 01 00 00             jne 001C8237   ; bypass native INT block
001C808A  8B 0D 84 02 E6 00             mov ecx,[00E60284]
001C8090  3B 4B 38                      cmp ecx,[ebx+38]
001C80C4  D9 05 0C 02 E6 00             fld [00E6020C] ; native INT, forward-pass path
001C8312  B9 A0 FC E5 00                mov ecx,00E5FCA0
001C8317  E8 74 08 E8 FF                call 00048B90  ; common RNG, patched here
```

The regression pins these native instructions independently of the emitter.
It also executes the unmodified `B80F0` release and its `B6DA0` callee in phases
2 and 4 with live state 14: kind 2 becomes 3; kind 4 stays 4. This is a bounded
native state-transition check, not a complete kickoff, punt, or onside replay.
Onside selection does not alter this ball-kind gate; the catch fix does not
add a playbook-type or phase predicate.

Ghidra corroboration under the supplied
`/media/noah/Storage/for codex 1.0/research/functions/nfl2k5/pseudo_c/`:

- `shard_003584_004095.c`: `FUN_000b6700`, `FUN_000b6740`,
  `FUN_000b73b0`, `FUN_000b80f0` (kind assignments and live release).
- `shard_004096_004607.c`: `FUN_000ddca0` (release-to-`A0910` chain).
- `shard_003072_003583.c`: `FUN_000a0910` (call to `B80F0`).
- `shard_008192_008703.c`: `FUN_001c78d0` (forward-pass guard and shared roll).

## Fix, allocation decision, and byte diff

The 48-byte main cave is completely full; simply inserting the selector would
overwrite scorebug floats at `0x10A40`. The chosen growth path uses the final
22 unused bytes of the same existing boot-logo bitmap, `0x10CAC..0x10CC2`.
The EDGE legend ends at `0x10CAC`, and the retail bitmap ends at `0x10CC2`.
No `.text` cave, XBE section growth, allocation request, runtime variable,
neighboring-owner edit, preset change, or protected dispatcher edit is added.
This layout is documented in the writer and pinned in `_sites()`.

`cave_bytes()` replaces just its five-byte offense-team load with a jump to
`kick_gate_bytes()`. The helper initially loads the original offense team.
For kind 3 it replaces that value with `[ebx+0x38]`, the catcher's own team,
then jumps back to the existing comparison. That comparison now selects the
existing Catching branch for kicked balls. Its controller load uses the
catcher's team, so CPU returners get CPU Catching and human returners get
Human Catching. Same-team recoveries take that branch too.

The RNG call and every arithmetic instruction in the main cave remain
byte-identical. Non-3 kinds return the original team to the original comparison;
the helper's flags are immediately overwritten. The helper adds no stack
operations and changes only EAX/flags. Kind-3 backward passes also receive
Catching rather than Interception, consistent with retail's non-forward guard.

Main cave, `0x10A10..0x10A40` (beta-63 authored bytes -> fixed authored bytes):

```text
before: e87b810300a18002e6003b433875168b50306a0459e8c6ae1600d8c0d8f9dbe9dbc1ddd9c3d9050c02e600d8c0def9c3
after:  e87b810300e9920200003b433875168b50306a0459e8c6ae1600d8c0d8f9dbe9dbc1ddd9c3d9050c02e600d8c0def9c3
```

Tail helper, `0x10CAC..0x10CC2` (retail bitmap pin -> new code):

```text
before: 034373a3d3f3e373130b03235347030749130749030d
after:  a18002e600833dc002e6000375038b4338e958fdffff

00010CAC  mov eax,[00E60280]
00010CB1  cmp dword [00E602C0],3
00010CB8  jne 00010CBD
00010CBA  mov eax,[ebx+38]
00010CBD  jmp 00010A1A
```

`status()` requires all five sites to match either retail or the exact new
installation. `apply()` replays an exact installation with unchanged payload
and `changed_bytes=0`; mixed, foreign, and old beta-63 installations are
refused. Old installed discs must be rebuilt from retail. The existing
`_apply_all` dispatcher already handles this new writer and its boot-logo
relocation; replay there was also byte-identical.

The new header-reference audit finds no foreign reservation, decoded absolute
operand, aligned data pointer, or bytewise relative-transfer target into the
22-byte helper. Raw unaligned code words that resemble header addresses were
inspected: they are instruction encoding fragments or relative offsets, not
absolute header references. The existing boot-logo relocation still handles
the kernel's boot-time bitmap read.

Retail SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Catch-writer-only patched SHA-256:
`1a5ca969c9cf215af5174988d3212e5b4bbb10ac3682150e8278f1187d2ca51f`.
The writer changes **96 bytes** versus retail, including the recomputed
`.text` digest (section 0), without changing file length. All section digests
verify. This hash is the bare catch writer's result, before boot-logo relocation
or other preset patches.

## Verification

The new regression gives **8/8 in every kicked-ball cell** of the table above.
Forward-pass rows remain exactly the red table's counts. Additional cases
verify Catching 0/25/50/75/100/200 for human and CPU catchers on both sides of
the possession predicate, with a different opposing-side factor to expose
wrong-team selection. Existing forward-pass cave arithmetic tests remain green.
This preserves the existing Catching arithmetic, including its floating-point
edge behavior; the boundary table uses Catching 50, as explicitly stated above.

The shared Unicorn loader now merges adjacent mapped page ranges. It maps the
same file-backed pages while avoiding thousands of individual mappings per
draw. Existing `_run` callers retain their defaults; new arguments select ball
kind and the non-possession team's controller. The synthetic throw-tuning
fixture includes the new retail tail pin and checks zero-byte replay.

Completed standalone commands and output tails:

```text
$ PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_catch_slider_kicks.py -v
kind=4 catch_slider_only: 0/8 | 4/8 | 8/8 | 8/8
kind=4 dynamic_and_catch_slider: 0/8 | 4/8 | 8/8 | 8/8
kind=3 catch_slider_only: 8/8 | 8/8 | 8/8 | 8/8
kind=3 dynamic_and_catch_slider: 8/8 | 8/8 | 8/8 | 8/8
Ran 8 tests in 72.002s
OK

$ PYTHONPATH=. python3 tests/nfl2k5_catch_cave_emulation_test.py -v
Ran 3 tests in 1.007s
OK

$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/nfl2k5_throw_tuning_test.py
Ran 39 tests in 10.332s
OK (skipped=1)

$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_discord_bugs_1.py DiscordCoreTests.test_B7_PROVED_retail_catch_patch_replay_is_byte_identical -v
Ran 1 test in 0.738s
OK

$ python3 packaging/repin.py --apply
[1] mod_editor/core/providers.py: mod_editor/core/nfl2k5_catch_slider.py
    c69f022b6328abcb0dcb74fef277297ac6d6471a96790559ef43ecc7cae26abe
 -> 0ea12e1f558463538a154f50c38036389a8c0432c7ba55ac2862cd706b85498f
applied 1 pin update(s)

$ python3 packaging/repin.py
would apply 0 pin update(s)
```

The throw-tuning suite's one skip is its pre-existing private **patched disc
image** smoke test; the retail XBE tests executed. At this base the old catch
writer unit tests live in `tests/nfl2k5_throw_tuning_test.py`; the new standalone
regression supplies the requested `tests/mod_editor/test_nfl2k5_catch_slider*.py`
entry point. Full local logs are in `.scratch/hf63-catch-slider-final.log`,
`hf63-catch-cave-suite.log`, `hf63-throw-tuning-suite.log`,
`hf63-production-replay.log`, and the `hf63-repin-*.log` files.

Full XBE memory-write gate (`.scratch/hf63-memory-writes.log`):

```text
$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_xbe_patch_memory_writes.py
Ran 111 tests in 1164.867s
OK
```

Full XBE cave-reference gate (`.scratch/hf63-cave-references.log`):

```text
$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_xbe_patch_cave_references.py
Ran 123 tests in 1327.252s
OK
```

Both gates passed without skips, including normal and reverse installation
orders on both allocation layouts. `git diff --check` also passed. No test gate,
retail pin, or source-drift guard was disabled or relaxed for this fix.

## Protected-file handoff

`python3 packaging/repin.py --apply` was run and updated one integrity pin,
in `mod_editor/core/providers.py`. Claude must regenerate
`data/nfl2k5_cave_reservations.json`; it was not edited, per the supplied rules.
`WIRING.md` gives the exact span, source hash, and full regeneration command.
The release manifest's old image/source receipts are not being represented
as a fresh acceptance build. No other protected file needs a change.

## Exact xemu witness for Noah

1. Rebuild from the clean retail source with this hotfix, first Basic and then
   Advanced and Experimental. Do not patch an old beta-63 output in place.
2. In the game's Custom sliders set **Interception 0**, **Human Catching 50**,
   and **CPU Catching 50**. Keep teams, rosters, weather, and other settings
   fixed. Assign the controller to the kicking/punting team; the receiving
   team must remain CPU-controlled.
3. Kick a normal in-bounds kickoff that the CPU returner fields in the field
   of play. Observe the catch and start of the return, avoiding a touchback
   or an intentionally uncaught ball. Repeat for a punt with CPU fielding.
   **Expected: the CPU can secure the catches and return; INT 0 must not force
   every eligible kickoff/punt fielding attempt into the muff/deflect outcome.**
4. Repeat the matched kicks and punts at Interception 50. Changing only that
   slider should not impose the old deterministic rejection at 0. Include an
   eligible CPU onside recovery to check the same kind-3 route under its native
   recovery rules. Ordinary catch eligibility, contact, ratings, and animations
   still apply; this patch does not force every possible fielding into a catch.
5. Reverse controller ownership and use different Human/CPU Catching values
   (for example 100/50, then 50/100) to confirm each returner follows its own
   side. As a control, throw forward passes with INT 0 and 50: interception
   scaling and offensive Catching must retain their prior behavior.

Offline tests prove the selector, native decision boundary, patch composition,
and byte/ownership contracts. No full gameplay or xemu result is claimed.
