# Beta 71: the 2026 scorebug wings at the broadcast's proportions with ESPN's marks (2026-09-15)

Branch `fable/b71-scorebug-wings` on top of `fable/b71-scorebug` (bcb0fcdf: timeout dashes on the records the retail
game binds to each team, event slabs on the charcoal tile). Proved offline by the native renderer; unwitnessed in game.

## What was wrong

- The wing boxes measured from the broadcast are 263x110 source px (87.7x45.6 HUD px, 1.92 to 1). Beta 70 drew each
  wing as one quad sampling a 128x32 texture (4 to 1) that baked the colour fade and the logo, so every logo was
  squeezed to 48 percent of its width; the widescreen option's 27/32 HUD scale narrowed it further.
- The 32 logo files were 128x128 approximations; the broadcast uses ESPN's own marks.
- The plate box was 6 px too wide on each side and 5 px too tall (row scans of frames 9001, 12001 and 15001 give
  x 837..1084, y 947..983).

## Measurements (source px, 1920x1080 frames)

| Element | Broadcast | Beta 70 | Beta 71 |
| --- | --- | --- | --- |
| Away score centre | 753 | 755 | 755 (kept) |
| Home score centre | 1165 | 1165 | 1165 (kept) |
| Away dashes | 718..765 | centred at 755 | kept (the dash glyphs belong to the font line) |
| Plate | 837..1084 x 947..983 | 830..1090 x 946..988 | 837..1084 x 947..983 |
| Away logo | about 460..635 x 946..1037 | squashed 4:1 art | box 455..625 x 946..1037, aspect-fitted |
| Home logo | about 1285..1462 x 946..1037 | squashed 4:1 art | box 1290..1460 x 946..1037, aspect-fitted |

## What beta 71 builds

- `data/nfl2k5_scorebug_mnf/logos/*.png`: the 32 marks fetched from `https://a.espncdn.com/i/teamlogos/nfl/500/<abbr>.png`
  (the same marks the broadcast bar uses), alpha-cropped and rendered at 64x64 with a one-pixel margin. Re-catalogued in
  `packaging/nfl2k5_scorebug_template_pngs.json` (size, sha256, width, height); catalog hash re-pinned.
- `exact.mnf_panel(team, side)`: a 64x64 RGBA wing texture, the logo in rows 0..33 (aspect-fitted into 62x32) and the
  team-colour ramp in rows 44..63 (team colour at column 0 to bar charcoal by column 44, smoothstep). Encoded by
  `art.runtime_panel(..., size=(64, 64))` with the template's own 64x64 format word (0x06610B29); the span stays
  5,280 bytes, so the appended volume is unchanged at 66 textures, 0.35 MB (the Berman freeze was volume-driven).
- `exact.mesh_mnf`: each retail wing object is one 32-vertex strip with repeated ids. A search over the retail strips
  found two clean quads per wing plus a collapse map that leaves every other triangle degenerate
  (`MNF_WING_LAYOUT`): the first quad stretches one ramp row across the whole wing (mirrored for the home side), the
  second draws the logo rows at the measured box near the outer edge, half a unit in front. Verified: exactly four
  visible triangles per wing (`test_wing_strips_draw_exactly_the_fade_and_logo_quads`).
- The renderer (`tools/nfl2k5_scorebug_exact.py`) binds the same 64x64 spans the compiler appends. Renders at 4:3 and
  widescreen: `docs/scorebug_mnf/wings/render_43.png`, `render_wide.png`; the KC texture: `kc_wing_texture_4x.png`.
- Pins regenerated (RUNTIME_SCENE_SHA256, RUNTIME_PINS, PROBE_APPEND_PINS["mnf"]); `MNF_VERSION` = scorebug-mnf-2026-v2.

## Not changed, and why

- The owner (`nfl2k5_scorebug_runtime.py`) is untouched: it still binds one texture per side to the wing material, so
  no code-cave growth, no manifest change, no XBE gate rerun for this line. The tint-by-owner design in the brief was not
  needed: the ramp rows carry the team colour, and a second material per wing would have needed scene surgery.
- Widescreen: the build compiles the wings once for both aspects and cannot pre-stretch them; the 27/32 squeeze applies
  to the whole HUD, logos included (visible in `render_wide.png`).
- The clock capsule text and the timeout dash glyphs belong to the font line; the capsule anchors were kept.

## Unproved

In-game appearance (the renderer is the proof), and the logo size relative to ESPN's (the box is ESPN's; tall marks
such as the Raiders shield fill about 78 percent of the wing height, wide marks the full box).
