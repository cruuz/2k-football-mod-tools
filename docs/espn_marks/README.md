# ESPN presentation marks (2026) (experimental)

The official presentation PNGs are now supplied through the [separate marks pack](../official_marks_pack.md). Without it, leave this option off to retain retail art; an explicitly selected build refuses cleanly. Historical art notes below describe the pack inputs.

Beta 76. Option `espn_marks_2026` (Build tab, "ESPN presentation marks (2026)"), off in every preset, needs a disc
image. Owner `mod_editor/core/nfl2k5_espn_marks.py`; art `data/nfl2k5_espn_marks/`; pins
`data/nfl2k5_espn_marks_pins.json`. The typed backend and the explicit GAMEDATA inventory are
`mod_editor/core/nfl2k5_presentation_standalone.py` and `data/nfl2k5_presentation_standalone.json`.
EXPERIMENTAL and UNWITNESSED in game: every claim below is an offline byte receipt or decoder read-back.

Review images are retained in private development evidence.

## What it changes

Four standalone TXTR chunks of `gamedata.iff` (outer 346, name id `0x00B6926C`, pack 0). Each is compiled at
build time from the user's own retail span and the shipped PNG, written as a complete resource inside its retail
span, and read back. The 32-byte wrapper (scratch word +0x14 included) and the 128-byte system/descriptor region
stay byte-identical, the decoded RGBA equals the PNG, and no allocation grows.

| Mark | Chunk, pack 0 offset, span | Retail | 2026 art | Grade |
| --- | --- | --- | --- | --- |
| `nfl_chiclet` 64x64 | 24, 0x6904E60, 4,368 B | pre-2008 NFL shield on a royal blue chip | the flat NFL shield of the 2026 MNF replay stinger (five-still registered median) on eight radial bands of its own navy | A |
| `shield_espn` 128x64 | 26, 0x6906050, 5,952 B | chrome ESPN oval with a red keyline, black letters | the red ESPN wordmark of the 2026 replay stinger, laid into the retail two-row wrap | A |
| `espnLogo1` 256x256 | 33, 0x690C740, 6,240 B | white ESPN wordmark wrapped across two rows | the 2026 scorebug wordmark (beta 72 art, 1,523-frame median) in the same wrap | A |
| `z_ESPN_bug` 64x64 | 57, 0x693E250, 4,064 B | chrome ESPN oval split across two rows | the same wordmark split across the same rows (beta 72 art) | B |

## Why shield_espn was redrawn: the retail wrap

`shield_espn` is not one picture. Every scene that binds it draws two slanted triangles whose UVs split the texture
along its diagonal: the upper-right triangle of the texture becomes the left half of the logo and the lower-left
triangle becomes the right half, raised a row. The score_bug scene (chunk 78, `zz_ESPN_bug` vertices 268..273) uses

| Triangle | Screen (score_bug units) | UV (-1..1) |
| --- | --- | --- |
| left | (-70.419, 7.371), (-70.419, 44.921), (-137.554, 44.921) | (0.9585, 0.9677), (0.9585, -0.998), (-0.998, -0.998) |
| right | (-3.116, 19.858), (-70.419, 57.512), (-70.419, 19.858) | (0.998, 0.998), (-0.9636, -0.9728), (-0.9636, 0.998) |

and the replay overlay (chunks 64 and 65, material `i_espn_logo_shader1`) and the `voice_of` and `weather_3row`
overlays in `overlay.cdf` draw the same two UV triangles at 1.36x and 1.49x. The beta 72 art (the wordmark rotated
-15.2 degrees across the whole texture) comes out of those triangles torn ("PTES"), the failure the Suzy Kolber
cut-in showed on 2026-09-03 with a whole-texture repaint. The retail logo's display ellipse measured through the
score_bug triangles is centred at (-70.62, 32.33) with semi-axes 37.92 x 11.99 units; the 2026 wordmark sits at
that centre, 56.6 x 14.2 units (94 percent of the largest width inside the ellipse), and every texel is
inverse-mapped through the triangle that owns its UV. Rendered back through the triangles it reads whole
(IoU 0.975 against the intended mark at half coverage, nothing outside the triangles). `SHIELD_ESPN_WRAP` in the
owner module carries the triangle numbers; the test reassembles the shipped PNG through them.

## 2026 sources and grading

Frames: the 2026 Week 3 Giants at Rams ESPN MNF highlights (764 stills, every 30th frame) and Noah's off-air
recording (3,129 stills at 2 per second). Broadcast frames never enter the repository; only authored art does.

- **espnLogo1, z_ESPN_bug (no re-author).** The beta 72 wordmark template (100x24 temporal median of 1,523 Week 1
  frames) matches the Week 3 scorebug wordmark at the same pixel-locked box (910, 955): 46 highlight stills,
  correlation median 0.997, best 0.999 (`frame_000290`); 215 off-air stills at (910, 956) (the recording's one-row
  offset), median 0.962. The second instance at (292, 955) in 24 highlight stills (0.986 to 0.990) is the same mark
  in the compressed bar of the TOUCHDOWN state; two more stills catch it sliding between the two positions.
- **shield_espn, nfl_chiclet (re-authored).** The 2026 replay transition is the ESPN MNF shield stinger: red ESPN
  wordmark on black, a silver MNF band, a flat NFL shield. It is small at obs 326, 680, 2349, 2537 and full size at
  obs 327, 681, 2350, 2538 and highlight 87, then the replay starts. The five full-size stills were registered onto
  highlight 87 (template scale 0.75 to 0.94, ECC affine refinement) and median-combined. The wordmark is 353 x 88
  source pixels (a downsample, where beta 72 upsampled 4.8x); the shield is 127 x 170 (2.7x downsample onto the
  retail footprint (9,2)-(55,63)). Red: RGB (191, 13, 19), the median letter colour. Plate navy: (39, 82, 123).
- **Grade decisions.** `z_ESPN_bug` is B, the espn_marks README grade, not the A of the research catalog: no scene
  material resolves to it (the overlay binding table at XBE file 0x502D44 names it, but the only material that
  matches is the score_bug's `zz_ESPN_bug`, which the scorebug's own table binds to `shield_espn`), so the two-row
  split is inferred from the retail art. `shield_espn` rises from B to A: a native multi-frame 2026 source and a
  wrap traced on every consumer. `nfl_chiclet` rises from B to A: the flat graphics-package shield and the
  multi-frame median the beta 72 README asked for. `espnLogo1` stays A.

## Encoding (VC-LZ bytes; stored body, fill padding, scratch word and the measured minimum scratch)

| Mark | Stored body | Retail stream | Beta 72 art (r2 proof) | Shipped 2026 art | Scratch word / minimum |
| --- | ---: | ---: | ---: | ---: | ---: |
| `nfl_chiclet` | 4,336 | 4,327 | 2,965, filled 4,321 + 15 | 2,792, filled 4,332 + 4 | 144 / 4 |
| `shield_espn` | 5,920 | 5,916 | 2,267, filled 5,911 + 9 | 1,736, filled 5,906 + 14 | 112 / 4 |
| `espnLogo1` | 6,208 | 6,198 | 5,068, filled 6,194 + 14 | same art, same bytes | 16 / 12 |
| `z_ESPN_bug` | 4,032 | 4,019 | 1,206, filled 4,021 + 11 | same art, same bytes | 80 / 0 |

Palette entries: 48, 32, 57, 60. GAMEDATA stays 2,977,184 bytes; only chunks 24, 26, 33 and 57 change.

## Refused, with the reason in every receipt

`telecircle1`, `telecircle2` (grade C: the 2026 telestrator draws yellow freehand strokes, highlight stills 165 and
166, not a ring; a re-vectored retail ring is not a broadcast still), `passicons` (controller glyphs),
`replayicons` (replay transport glyphs), `endQTR_textures` (consumer untraced; no end-of-quarter card in either
frame set), `score_buga` (the retail scorebug plate atlas; consumer UV rects untraced, superseded by the sprite
scorebug). `espn1` and `nflShield1` are DXT1 and have no writer. The other 34 GAMEDATA textures have no graded art.

## Typed build (unified provider)

`extended_standalone_inventory()` is the explicit view: the 11,395 shipped All Textures records plus the 44 GAMEDATA
rows, 11,439 catalogued, 11,437 format-supported, 11,399 offered. A project edit of kind `p8_texture` with asset id
`p8:346:nfl_chiclet`, `p8:346:shield_espn`, `p8:346:espnLogo1` or `p8:346:z_ESPN_bug` builds through
`build_unified_presentation_mark_imports` with the same staged shape as the All Textures lane; any other `p8:346:`
id is refused with its reason. The Build option and a project edit of the same mark cannot both write it: the
option refuses a mark that is neither retail nor its own 2026 bytes.

## Status, revert and conflicts

`python3 -m mod_editor.core.nfl2k5_espn_marks status <image or extracted folder>` prints retail, applied, mixed or
foreign. Off does not restore an already-2026 source; `python3 -m mod_editor.core.nfl2k5_espn_marks revert <image>
--retail <retail image>` writes the four retail spans back from a retail source after checking their pins.

The v7 ESPN scorebar writes only `score_bug` and `score_buga` in place and points its own mark at its atlas, so it
composes with this option.

The sprite scorebug composes too (beta 76, job c1), in either build order, on one disc. The sprite appends its
textures and scene to the end of `gamedata.iff` and leaves these four spans where they are. The compatibility rule:

- The sprite reads `gamedata.iff` as its supported base when every byte outside the four spans is retail (a SHA-256
  of the retail HUD with the four spans cut out, `HUD_OUTSIDE_ESPN_MARKS`, next to its `hud_before` pin) and each span
  holds its retail or its applied pin from `data/nfl2k5_espn_marks_pins.json`
  (`nfl2k5_scorebug_sprite.hud_espn_marks`). Install, read-back and the inspector all use it.
- This option reads a grown `gamedata.iff` only when the sprite recognizes the whole outer as its own install: that
  HUD plus exactly its appended collection for the layout the build used
  (`nfl2k5_scorebug_sprite.gamedata_status`). Status, apply, verify and revert take `sprite_folder`; the Build passes
  the scorebar artwork folder when the sprite scorebug is on. Receipts say `gamedata_appended: sprite scorebug`.
- Anything else still reads as foreign: another byte of the HUD, a span at neither pin, any other growth. The
  diagnostic runtime probes (`full`, `mnf` and the rest, never Build options) keep their byte-exact `hud_before` and
  `hud_after` pins.

Both orders give the same pack 0 byte for byte. The revert writes the retail spans into the live copy of pack 0; a disc
built marks-first keeps the 2026 spans in the dead pre-sprite copy that the sprite transaction leaves behind, which no
directory entry points at.

The option still refuses the Hi-res pack's scorebug family. It rewrites `shield_espn`, and skipping that one texture
would not be enough: the family also rewrites `score_buga` (chunk 53), and the Hi-res writer re-lays `gamedata.iff`
around the new chunk, so `z_ESPN_bug` (chunk 57) moves and the outer's size changes (the retail art upscaled grows
chunk 53 from 2,432 to 4,368 bytes at 2x and to 2,464 at 1x), while these marks, their status and their revert are
pinned to the retail layout. The sprite scorebug refuses that family as well.

## Witness list

1. An instant replay: the ESPN logo on the replay overlay is the red 2026 wordmark, whole, not torn.
2. The retail field scorebug (no scorebar options on): the ESPN mark at the bar's left end is the red wordmark, on
   both drive directions.
3. The weather and "voice of" overlays (pregame): the ESPN logo is the red wordmark, whole.
4. A graphic that shows the NFL league chip: the current eight-star shield on navy.
5. Wherever `espnLogo1` and `z_ESPN_bug` appear: a white ESPN wordmark, whole. Their consumers are untraced, so a
   torn or cropped wordmark there is the thing to report.
6. On a disc built with the sprite scorebug as well: items 1, 3 and 4 again, and the sprite bar itself looking and
   counting as it does on a disc without this option.

## Provenance scripts

`reports/b76_p1/author_marks.py` rebuilds `shield_espn.png` and `nfl_chiclet.png` byte for byte from the private
frame folders and an extracted retail pack 0 (geometry only); `reports/b76_p1/author_marks_report.json` holds the
registration warps and every number above. `reports/b76_p1/render_preview.py` draws `marks_preview.png` from the
shipped PNGs alone. `reports/b76_p1/seal_png_catalog.py` adds the four PNG rows to the reviewed release catalog and
reseals its checker pin.
