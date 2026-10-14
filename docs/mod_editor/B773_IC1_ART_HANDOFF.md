# ic1: remaining icon and fan-cap artwork work

The native Denver schedule-icon correction is implemented in
`mod_editor/core/nfl2k5_menu_icon_orientation.py`. This document is the art handoff
for the remaining N17/N18 findings. No new logo or cap artwork was drawn by ic1.
Evidence filenames below are relative to the job's `evidence/` directory.

## N17: mini icons and their other consumers

The base-disc census covers all 32 current clubs: 64 mini icons at 64x64 and
128 larger helmet cards, two views each at 128x128 and 256x256. See
`icons_and_cards_0.png` through `icons_and_cards_3.png`, `audit.json`, and
`cards_audit.json`. The JSON records resource hashes, virtual offsets, sizes,
and alpha bounds. `suspects.png` compares potentially confusing marks at 4x.
The original 2026 miniature authoring path is
`tools/nfl2k5_team_logos_2026.py:cmd_minis`, using
`tools/nfl2k5_mini_helmet_blender.py`. The Studio imports those PNGs through the
P8 visual-project writer. The minis use their own art and camera, independently
of the larger `helm_*` cards.

Confirmed defects:

* `mini.cdf`, `mini_a08_0`, Denver: the horse is upside down, although the shell
  is upright. The upright `mini_h08_0` supplies the byte-pinned mechanical repair.
  The entire opposite view is reflected, including its lighting and small shell
  details. The result is not a newly rendered right-side helmet. See
  `DEN_schedule_{before,after}_{native,4x}.png` and
  `DEN_composite_{before,after}.png`. The latter are offline alpha composites over
  schedule-row grey and selection blue, not captured game frames.
* `mini.cdf`, `mini_a22_0`, Pittsburgh: the yellow hypocycloid is below the blue
  and red is to the left. The larger `helm_a22_0` cards have the proper ordering.
  `mini_h22_0` is intentionally blank on the other side, so reflecting it would
  erase the Steelers mark. Re-render this 64x64 view from the existing upright
  current helmet art, keeping a transparent background and the miniature camera.
  Do not flip the whole icon or mirror the lettering. Reference: the base disc's
  128/256 `helm_a22_0`, the existing PIT logo asset, and `suspects.png`.

Review before further edits:

* SF `mini_a25_0`: small lettering appears reversed relative to the larger card.
  Compare its 4x crop in `suspects.png` to `helm_a25_0` and the existing SF mark.
  This is a review flag, not a verified rotation diagnosis or an applied repair.
* The initial Giants lettering concern did not survive the larger comparison:
  its slant follows the view and the `ny` remains readable. No Giants fix is
  proposed. The C/G/W marks likewise must not be blindly mirrored to make a
  directional helmet logo. Review geometry and legibility against the existing
  larger cards, not generic whole-image transforms.
* Some mini alpha bounds reach x=0 or x=63. That alone does not prove cropping.
  No new cut-off shell or facemask was established by the offline census. Do not
  invent new framing from that numerical boundary test.

`mini_loader_strings.json` records all 22 miniature formatting-string instances
in the base XBE. Nearby labels identify the schedule family (regular season,
playoff, Super Bowl and offseason), League Calendar, MyNFL status/playoff
seeding, ESPN25th Anniversary, and Online User Card/spreadsheet. Other occurrences
sit near draft/rookie-signing and situation-data strings. These are static
consumer clues, not a complete call-graph proof or a claim that every screen was
visited. All requests for repaired member `mini_a08_0` resolve to the same corrected
bytes; historic styles and other members are unchanged. Live proof was forbidden.

## N18: this is opaque cap artwork, not an alpha/mip edge defect

Inputs checked directly: the N18 video stills at 28:45 and 28:48, the base disc,
`tools/b77/fr1_fan_art.py:tshirt`, and the shipped
`data/nfl2k5_modern_fans/<TEAM>/tshirt.png` files. All 3,040 textures in the four
crowd-set families of all 32 current clubs were decoded. All four `tshirt`
copies for each club are byte-identical, all cap panels have alpha 255 throughout,
and their P8 textures have exactly one mip. Receipts: `audit.json`,
`cap_audit.json`. Review sheets: `fan_gear_0.png` through `fan_gear_3.png`,
`audit_0.png`, `audit_1.png`. Per-team native and 4x cap crops are
`<TEAM>_cap_native.png` and `<TEAM>_cap_4x.png`.

The light diagonal/rectangular patch is already present behind the mark in the
opaque source PNG. It survives P8 encoding; changing transparent RGB or mip
filtering cannot remove it. For TEN, decoded front-background samples at (198,15)
and (252,15) are RGB (75,118,172) and (14,37,67), respectively. The authoring function
uses retail-derived luminance, normalizes it over the shirt body and cap together,
then places the new logo on that backing. The logo is not the sole changed pixel
region. A new backing must be authored or approved; a broad luminance threshold
would also damage legitimate logo colours.

Exact target and UV constraints:

* `tshirt`: 256x128 RGBA source, compiled to P8, one mip. Front/logo panel is
  x=192..255, y=0..47, corresponding to u=0.75..1, v=0..0.375.
* The cap samples more than that panel. Base scene `crowda`, outer 2532, chunk 9,
  material `cap`, has 105 referenced vertices with UV range
  (0.7571021,0.0076092) to (0.9935029,0.5668156). Twenty-nine sample y>=48.
  `cap_uv.json` retains the decoded coordinates. This is one actual cap mesh,
  not proof that every cutscene variant has identical UVs.
* `nfl2k5_modern_fans.KEEP_RECTS['tshirt']` restores x=192..255, y=48..73 from
  the input disc, as well as the separate sneaker region x=158..191, y=0..73.
  The first rectangle is not unused padding: cap geometry samples it. Retained
  swatches can contribute to the cap's other surfaces. Exact in-game colour also
  depends on vertex/material shading; their role in the reported light-blue patch
  is not separately proved. Do not blindly delete both KEEP_RECTS regions.
* Keep the existing club mark, its placement and size: authoring centre (225,24),
  fit box 42x34 at native size, 4x master scale. Do not redraw the logo. Separate
  backing, shading, logo and cap swatch treatment so opaque paint does not carry
  a contrasting rectangular background onto the mesh. Preserve the shirt body.
* Start with TEN. Review all 32 clubs before accepting the revised backing.
  Sixteen have at least 16 levels of left/right background median contrast in
  the recorded edge sample boxes: BUF, CHI, DAL, DEN, GB, JAX, KC, MIN, NYG,
  NYJ, PIT, LAC, TEN, WAS, CLE, HOU. That is a repeatable screening metric, not
  sixteen independently witnessed in-game defects. The other sixteen still
  require cap-swatch and mesh review.
* Update every changed team's four sets through the existing fan compiler:
  A=1822+i, B=1907+i, ns=2162+i, tg=2247+i, where i is the asset-code position in
  `tools/b77/fr1_record_pins.py:ORDER`. Use the existing `pins.json` per-part names,
  IDs, offsets, palette limits, wrapper and scratch checks. Re-record only reviewed
  changed parts. Include native/4x source and encoded readback, cap-mesh views,
  replay, scope and Studio equality. Do not reuse quantized old swatches as a
  retail source for a fresh Studio-equality claim.

No clothing, fan logo, cap panel, crowd scene, or fan pin was changed by ic1.
The N18 repair remains with the Opus art job. The isolated cap diagnostic render
attempt was not useful and is not presented as evidence; the UV census and actual
playtest stills provide the mapping and visual evidence instead.
