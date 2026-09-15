# Beta 71: Modern colour and lighting, calibrated from the first in-game measurement (Claude Fable 5.1, 2026-09-15)

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

## 4. The far-field shimmer

`detail_normal` (512x256 P8) ships a full mip chain (175,872 bytes) and every level shares its one palette, so the palette
flatten is consistent across distance; the 40 percent flatten lowers the bump amplitude 27 percent below beta 70 and
60 percent below retail, which lowers both the darkening and any detail-layer shimmer. Whether the shimmer seen at high
internal resolution is retail behaviour or the option's is UNPROVED: the far band of the screenshot carries more
high-frequency energy (0.065 normalised) than the mid field (0.042), which is what detail-layer aliasing looks like, and
retail draws the same layer. It needs an A/B at the same camera and internal resolution with the option off and on.

## 5. Tests and gates

{{RESULTS}}

## 6. What Noah should look at

1. Broncos at Chiefs, Arrowhead, night: the turf should read close to the broadcast green (107, 121, 53); compare a screenshot's field pixels with the earlier (51, 61, 32).
2. A 1 PM day game (Jacksonville, Nashville) and a dome (Lucas Oil), then rain and snow (extrapolated).
3. White uniforms and skin under the brighter rigs (clipping), and the far field at high internal resolution with the option off and on for the shimmer question.
