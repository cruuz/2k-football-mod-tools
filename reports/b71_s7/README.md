# Beta 71 S7: lit possession plate colours and the modern colour overall strength

Fable content fork, 2026-09-16, branch `fable/b71-s7-plate-and-half-colour` from S6 563e14e4.

## Verdicts answered (disc n, 04:36)
- "scorebug looks great! but 1st and 10 for dallas is black and hard to see"
- "color and brightness etc patch is too vibrant, cut it by half"

## Change 1: plate and wing colours as lit on air (`mod_editor/core/nfl2k5_scorebug_exact.py`)
`plate_rgb(team)`: the explicit near-black secondary or the primary, lifted in HSL to lightness `PLATE_LIGHTNESS_FLOOR`
0.36 (the measured KC plate top (178,12,60) under the 0.83 mask top), hue and saturation kept; black primaries (LV, NO,
PIT: `max(rgb) < 40`) light to neutral grey; then lightness is lowered until the white label keeps
`PLATE_LABEL_CONTRAST` 4.5:1 (+0.3 margin for palette quantisation) on the masked plate (`PLATE_MASK_LABEL` 0.788,
measured on the template's plate cell under the label rows). `wing_rgb(team)`: the measured DEN/KC lit wings or the
primary lifted to `WING_LIGHTNESS_FLOOR` 0.43. The words are written into the per-team logo TXTR padding by
`mnf_panel_span`; the XBE owner is unchanged (`nfl2k5_scorebug_runtime.py` untouched, appended resources only).
Proof: `prove_plates.py` renders every team's plate with the sprite preview (native execution) and measures the rendered
plate under the label: `plate_contrast.json` (min 4.74:1, max 13.98:1), `plate_contact_sheet.png`, `dal_kc_43_2x.png`,
`dal_kc_169_2x.png`, `bar_{DAL,GB,PHI,PIT,NYG}_43_3x.png`. Lowered for contrast: PIT gold (255,182,18) to (191,129,0),
NO gold (211,188,141) to (175,138,60), LV silver to (134,145,150), SEA green to (90,161,33). Compiler pins regenerated
(`regenerate_pins.py`, `compiler_pins.json`).

## Change 2: overall strength (`mod_editor/core/nfl2k5_modern_color.py`, page, docs, pins)
New control `master.strength` (group "Overall strength", first on the Colour & lighting page; default 0.5, Off value 1,
range 0..1). Every written value is retail + (broadcast - retail) x strength: `configured_rig` (all seven rigs' colours,
intensities and shadow scalar, so `modern_table` and the predictions agree), `regrade_palette` (colour maps, end zones,
outside, divots including alpha, material colour words through `regrade_colour_word`), `corrected_tint` (Fldd tint words
and vertex tints), `flatten_normal_palette` (flatten amount x strength), the outside link amount (`effective_link_amount`)
and the outside vertex falloff lift. 1.0 reproduces the previous Broadcast bytes exactly (`blend` returns the endpoint
values untouched); 0 returns retail bytes (proved: `strength_proof.json` `retail_identical` true for s13dd/s13ad/s13nd).
`data/nfl2k5_modern_color_pins.json` rebuilt at the default (477 bundles, 7 rigs); `verify_pins.py` rebuilds and compares.
Predicted Arrowhead turf (calibrated model): day (35,44,18) retail, (62,76,36) half, (90,105,60) full; afternoon
(26,30,12) / (53,61,32) / (88,103,60); night (41,51,25) / (68,82,37) / (103,122,51). Swatches: `strength_swatches.png`.
XBE rig bytes change at the default (all seven tables differ from both retail and the 1.0 values): the integration must
regenerate the cave manifest and run the XBE gates.
