# Corner watermark placement (N26)

The NFL and MNF variants share one quad. The default layout encloses their
broadcast ink in `(1655,35)-(1869,64)` at 1920 x 1080. The right margin is
51/1920 of the active picture width. `placed_box` preserves that fraction in
both display modes, retaining the same logo dimensions and vertical position.

Previously, the `top-right` pin used the contracted HUD edge minus 12 source
pixels, moving the wide right edge to x=1758. The new wide position is 111
source pixels farther right. In 4:3 the existing-size logo is reanchored to a
38.25-pixel right margin in the 1440 x 1080 display model.

The ordinary widescreen HUD clip would cut off the corrected placement. The
SPR5 update dispatch therefore stamps only the scorebug camera with the
existing widescreen pixel-HUD mode. This retains the full active-picture clip
and cull bounds, with unchanged projection and glyph scale. Ordinary HUDs
still use their contracted clip. Retail 4:3 does not consume the camera pad.

This position is relative to the active 640 x 448 target within the 720 x 480
framebuffer. It does not move graphics into the black perimeter or change
emulator display settings. The supplied broadcast marks sit about 2.8% from
the right and 3.4% from the top; they are outside a centered 4:3 crop and a 5%
inset guide. The 4:3 game position is an adaptation, not a center-cut broadcast.

Validation: `test_nfl2k5_scorebug_watermark.py` executes native projection and
camera activation at both aspects, checks repeat activation and verifies that
an ordinary HUD retains its original clip. `test_nfl2k5_hd1_repair.py` checks
bounded writes, refusal of unknown inputs, full-stream overlay hashing and
synthetic-image write/replay behavior. No new image assets are required.
