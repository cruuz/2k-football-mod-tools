# Beta 71: Modern colour and lighting, calibrated from the first in-game measurement (2026-09-15)

EXPERIMENTAL / UNWITNESSED. Branch `fable/b71-color2` (worktree `~/2k-worktrees/fable-b71-color2`, base `local/stack-beta-71`
= e2f5c6e6). Every number below is either measured from a screenshot or a broadcast frame, decoded from the disc, or
predicted by the calibrated model; nothing new has been watched in game.

## 1. What the beta 70 test showed

Two screenshots of the beta 70 build at Arrowhead at night (`~/Downloads/ksnip_20260915-132227.png`, `-132214.png`):
the drawn turf is RGB (51, 61, 32), HSV 82 degrees / 0.47 / 0.24. The broadcast field in the Monday Night Football
frames is (107, 121, 53), HSV 73 / 0.56 / 0.47 (752-frame median) and (95..119, 105..117, 52..63) in spot samples.
The field had to be about twice as bright and yellower. Beta 70 had moved the colour map only 4 percent in value and the
rig 12 percent, so the difference was invisible: the drawn field is far darker than "colour map times rig".

## 2. The calibrated model

flat = colour map x (ambient colour x intensity + sum over lights of colour x intensity), per channel.
drawn = flat x SCREEN_FACTOR. The factor is measured, not modelled: beta 70's map (109, 130, 75) under its night rig
(gain 2.56, 2.56, 2.58) gives flat (278, 333, 194) and drew (51, 61, 32), so the night factor is (0.183, 0.183, 0.165).
The 2026-09-07 retail day capture ((34, 43, 2) from map (100, 125, 66) under the retail day rig, gain (1.61, 1.67, 1.34))
gives the day factor 0.21 (blue collapsed under the yellow retail key, so day blue is taken from green). The module
carries both (`SCREEN_FACTOR`, `predicted_on_screen()`); the model reproduces (51, 61, 32) exactly.

## 3. What changed (all in `mod_editor/core/nfl2k5_modern_color.py`)

| Lever | Beta 70 | Beta 71 |
|---|---|---|
| Grass colour map and outside grass | hue pulled 35% toward 82, saturation x 0.90, value x 1.04 | hue pulled 50% toward 72, saturation x 1.12, value lifted through `1 - (1 - v)^2.8` (Arrowhead median (100, 125, 66) becomes (181, 216, 102): value 0.49 to 0.85, never clips) |
| Night and dome rig | ambient (0.94, 0.96, 1.00) x 0.42, three lights x 0.72 | ambient white x 0.50, three lights white x 0.86 |
| Day rig | ambient x 0.45, key 1.15, fill 0.30 | ambient x 0.58, key 1.20, fill 0.48 |
| Afternoon, rain, snow rigs | as beta 70 | about 10 to 12 percent stronger |
| Night tint (Fldd word and vertex colour) | 0xFFF8FCFF, (248, 252, 255) | neutral 0xFFFFFFFF, (255, 255, 255) |
| Grass bump map | flattened to 55% | flattened to 40% |

Predicted drawn turf: Arrowhead night (102, 122, 52) against the broadcast (107, 121, 53); a 1 PM day game (83, 99, 47)
against (88, 105, 61). One colour map serves every rig of a stadium, so night (the anchor) takes priority and day blue
stays a little low. Domes share the night table. Every refit stays inside its retail wrapper and fixed span as before;
the pins (`data/nfl2k5_modern_color_pins.json`) were regenerated for the new bytes.


## 3b. v2.1, from the first test of v2 (Jets at Chiefs, afternoon)

The v2 disc drew the playing surface at (79..91, 85..103, 32..46), value 0.33..0.41 against the broadcast's 0.41..0.47,
so the brightness landed; but the end zones and the area behind the goal posts were darker, the outside grass by the
benches darker still, the turf showed player-sized dark blotches, and the far field stayed noisy. Decoding the Arrowhead
afternoon bundle explained each one:

- The colour map is almost flat (luminance 111 with a standard deviation of 3), so the blotches are not in it. The field
  also draws a `divots` wear layer: 64x64 P8, mean colour (70, 88, 48), alpha 36 percent over 79 percent of its pixels.
  Beta 70 and v2 never touched it, so on a bright field it read as dark patches. v2.1 re-grades its greens like the turf
  and scales every alpha to 30 percent of retail (`DIVOTS_ALPHA`), as a fourth pinned site per bundle (refit inside its
  compressed span like the bump map).
- The six end-zone maps (`endzone_N_L/M/R`, `endzone_S_L/M/R`, three shared 256x128 P8 textures) and the centre logo carry
  their own green background; v2.1 re-grades their green palette entries (painted art untouched). The end-zone overlay
  shape kept the darker afternoon vertex tint (255, 238, 205); it now takes the softened tint like the grass.
- The outside grass texture is 45 percent darker than the field map (mean luminance 62 against 111), and its shape
  darkens toward the edges through grey vertex colours (255, 229, 204, 178). v2.1 lifts the outside palette by the
  ratio of the two textures' used-green means (1.46 at Arrowhead) and keeps only 45 percent of the grey falloff.
- The bump map flattens to 32 percent. Its palette was also being edited 128 bytes early since beta 70 (the texture
  descriptor's offsets are relative to the video section after the chunk's 128 system bytes), which left the last 32
  palette entries unflattened and wrote normal bytes over the smallest mip levels; v2.1 edits the right bytes and
  refuses if the palette is not where the descriptor says.

{{V21_RESULTS}}

## 4. The far-field shimmer

`detail_normal` (512x256 P8) ships a full mip chain (175,872 bytes) and every level shares its one palette, so the palette
flatten is consistent across distance; the 40 percent flatten lowers the bump amplitude 27 percent below beta 70 and
60 percent below retail, which lowers both the darkening and any detail-layer shimmer. Whether the shimmer seen at high
internal resolution is retail behaviour or the option's is UNPROVED: the far band of the screenshot carries more
high-frequency energy (0.065 normalised) than the mid field (0.042), which is what detail-layer aliasing looks like, and
retail draws the same layer. It needs an A/B at the same camera and internal resolution with the option off and on.

## 5. Tests and gates

Pins: `python3 -m mod_editor.core.nfl2k5_modern_color pins <retail extraction> --write --workers 8` (5 minutes here): 477 bundles, 7 light
tables; sites changed 1,175 of 1,431 (field scene 456 of 477, grass bump map 459 of 477, tint 260 of 477; the same 21 field
scenes and 18 bump spans keep retail bytes because their retail streams leave no room inside the wrapper).

Standalone runs on this branch (c9401398), `python3 tests/mod_editor/<file>.py`:

| File | Result |
|---|---|
| `test_nfl2k5_modern_color.py` (palette curve and direction, colour word, bump flatten, tints, rig definitions, retail XBE apply/replay/restore/foreign, Arrowhead night bundle equals its pin, pins cover 477 and the extraction reads retail) | 9 passed |
| `test_build_panel_qt.py`, `test_mod_build.py`, `test_phase1_packaging.py`, `test_b68_a1_audit.py`, `test_b69_a1_registry.py`, `test_product_catalog.py` | 13, 11, 23, 10, 7, 9 passed |
| `python3 -m mod_editor.capabilities.validate_registry` on the hydrated tree | PASS, capabilities=174 |
| `python3 packaging/repin.py --apply` | no pin changes (the module is not hash-pinned; it is in the runtime module list) |
| XBE gates, `test_xbe_patch_memory_writes.py` and `test_xbe_patch_cave_references.py`, run detached on this branch | {{GATES}} |

Test disc: `~/2K5 Mod Studio Builds/NFL 2K5 MOD TEST 2026-09-15c (colour v2 + 2026 scorebug + widescreen).xiso.iso`
(6,506,858,496 bytes, built in 400 s from this branch: Advanced preset plus modern colour v2, the 2026 scorebug and
Widescreen 16:9; its `.2k5patch` sits beside it, 199,041,472 bytes, 4,498 runs). Read back from the built image with
the new pins: light rigs `applied`, all 477 bundles `applied`. The builds folder holds three MOD TEST images (the rule's
maximum): 15a, 15b and this one.

## 6. In-game checks

1. Broncos at Chiefs, Arrowhead, night: the turf should read close to the broadcast green (107, 121, 53); compare a screenshot's field pixels with the earlier (51, 61, 32).
2. A 1 PM day game (Jacksonville, Nashville) and a dome (Lucas Oil), then rain and snow (extrapolated).
3. White uniforms and skin under the brighter rigs (clipping), and the far field at high internal resolution with the option off and on for the shimmer question.
