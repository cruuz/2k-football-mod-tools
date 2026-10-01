# ESPN 2026 wipes and boards (experimental)

The official presentation PNGs are now supplied through the [separate marks pack](../official_marks_pack.md). Without it, leave this option off to retain retail art; an explicitly selected build refuses cleanly. Historical art notes below describe the pack inputs.

Beta 76. Option `espn_wipes_boards_2026` (Build tab, "ESPN 2026 wipes and boards"), off in every preset, needs a
disc image. Owner `mod_editor/core/nfl2k5_espn_wipes_boards.py`; backend `mod_editor/core/nfl2k5_presentation_scenes.py`
(the raw MRKS transport adapter and the fixed-span SCNE refit); art `data/nfl2k5_espn_wipes_boards/`; pins
`data/nfl2k5_espn_wipes_boards_pins.json`; the art is rebuilt byte for byte by `reports/b76_p2/author_wipes_boards.py`.
EXPERIMENTAL and UNWITNESSED in game: every claim below is an offline byte receipt or a decoder read-back.

Review images are retained in private development evidence.

## What it changes

Fourteen embedded P8 textures inside six presentation scene resources. Geometry, material colours and dynamic
text are untouched. Each resource is compiled at build time from the user's own retail span and the shipped PNGs,
checked against its applied pin, written in place and read back; nothing grows (0 archive, RW-pool or GAMEDATA
bytes).

| Resource | Outer, slot or chunk | Pack:offset | Span | Shape | System / video | Scratch |
| --- | --- | --- | ---: | --- | --- | ---: |
| `replay_wipe` | 3114 (wipe.cdf), slot 1 | 4:0x1DE3D00 | 124,064 | raw MRKS | 77,824 / 46,208 | 0 |
| `fullscreen_WipeElectricity` | 3114, slot 3 | 4:0x1E20700 | 103,200 | raw MRKS | 80,640 / 22,528 | 0 |
| `fullscreen_WipeRedFlashy` | 3114, slot 4 | 4:0x1E3EC00 | 90,272 | raw MRKS | 23,680 / 66,560 | 0 |
| `scoreboard` (pause backdrop) | 347, chunk 5 | 0:0x6BABEB0 | 29,872 | VC-LZ SCNE | 9,088 / 45,056 | 16 |
| `helmetbumper` | 18, chunk 11 | 0:0xAAB030 | 79,344 | VC-LZ SCNE | 6,016 / 133,120 | 96 |
| `playercard` | 3, chunk 57 | 0:0x118D30 | 11,568 | VC-LZ SCNE | 17,792 / 15,360 | 112 |

| Texture (materials) | Size, mips | Retail | 2026 art |
| --- | --- | --- | --- |
| replay_wipe t0 `pattern_flash` | 32x32, 1 | white radial flash | the silver of the MNF band the 2026 transition flies through, brightest in the middle |
| replay_wipe t1 streaks (`z_ESPN01_flash`, `a_white_streak01`, `b_yellow_streak01`, `z_ESPN02_flash`, `foreground_streaks`) | 8x8, 1 | white bands | a glossy rim line: white-hot core in 2026 rim red |
| replay_wipe t2 `logo_glow_a/b/c` | 128x64, 1 | blurred white ESPN | the red 2026 wordmark with its own bevel shading, softened as a glow |
| replay_wipe t3 rays and crescents (`cruve_rays`, `top_rays`, `crescent01-03`) | 256x128, 1 | soft white arc | a glossy red rim along the same arc: dark inner edge, the stacked echo ridges, a bright top edge, a red glow |
| RedFlashy t0 `logo1` | 256x256, 1 | white ESPN in a two-row wrap | the red 2026 wordmark laid into the same wrap (ES over PN, slanted seam) |
| Electricity t0 `background1` | 64x64, 1 | navy two-tone | the 2026 MNF bumper's red wall over the emblem's black plate |
| Electricity t1 `lightning1/2` | 128x128, 1 | blue bolts | jagged lines drawn as the bumper's white-hot outline in a red glow, in the retail column layout |
| scoreboard t0 `sign02` | 128x128, 1 | Players Inc, NFL shield, ESPN VIDEOGAMES and ESPN VISION signs | the emblem's top half (red ESPN over the silver MNF band), vertical red ESPN banners, the 2026 NFL shield, a white ESPN MNF lockup, a white ESPN under the screen, silver frames |
| scoreboard t1 `dot` | 64x64, 1 | blue LED wall | the same 1-texel LED wall in the 2026 bar's rim blue |
| scoreboard t2 `sign01` | 128x128, 1 | amber LED VISITOR / HOME / DOWN and the SPORTSCENTER sign | white LED labels on dim bar blue, and an ESPN MONDAY NIGHT FOOTBALL marquee |
| scoreboard t3 `backboard01` | 64x64, 1 | blue stripes | the 2026 board charcoal with vertical grain |
| helmetbumper t0 `monitor` | 256x256, 6 | wooden monitor, blue field, gold lines | the emblem's black plate and red rim as the bezel, the red MNF bumper wall as the screen, the same line layout as white-hot outlines |
| helmetbumper t1 `monitorcolors` | 256x128, 5 | blue streaks | red ribbon bands with white glints |
| playercard t1 `znfl_shield` | 64x64, 1 | pre-2008 NFL shield | the flat 2026 NFL shield from the emblem |

## The two write routes

- **Raw MRKS (the three wipes).** wipe.cdf (outer 3114) holds six raw MRKS slots of 124,160 bytes: compression
  word 0, scratch word 0, stored body = system + video bytes. An MRKS points at a wrapper descriptor at +0x20 whose
  first relative pointer owns the scene descriptor; the parser reads a temporary SCNE view of it. The adapter
  replaces the pixel indices and palette of the chosen descriptors at their allocations and nothing else: the
  32-byte wrapper, the system buffer, every other video byte and the span size are byte-identical, and the slot
  padding after the span is never touched. There is no compression step.
- **VC-LZ SCNE (the scoreboard, the helmet bumper, the player card).** The stadium writer's encoder compresses the
  edited scene, the fill spends the spare length on literals at the front of the stream until it reaches the
  retail consumed length, the opaque tail is copied back, and the retail scratch word must still cover the
  in-place decode. The optimal parse is tried when the greedy stream cannot keep that scratch.

Every descriptor passes the stadium writer's `_target_contract` first: P8, flags 0x80000000, a complete halving mip
chain that ends exactly at its palette, no overlap with another descriptor, a decoded base level that matches the
parser. PNGs go through the Stadium Studio quantiser, swizzle and mip generation.

| Scene | Retail consumed | Stream after refit | Zero gap | Minimum scratch / retail |
| --- | ---: | ---: | ---: | ---: |
| scoreboard | 29,831 | 29,831 | 0 | 0 / 16 |
| helmetbumper | 79,297 | 79,297 | 0 | 5 / 96 |
| playercard | 11,524 | 11,524 | 0 | 100 / 112 |

`helmetbumper_monitorcolors` is row-constant on purpose: its regenerated mip chain stays at 28 palette entries, so
the resource ends in zero palette entries the stream packs as matches. With a full 256-entry palette at the very
end, the in-place decode needed 102 bytes of scratch against the retail 96.

## 2026 sources

Frames: the 2026 Week 3 Giants at Rams ESPN MNF highlights (764 stills, every 30th frame, and 30 fps frames of the
mnf 87 transition taken from the same video) and the off-air recording of the same game (3,129 stills at 2 per
second). Broadcast frames never enter the repository.

- **The replay transition** is the ESPN MNF shield stinger: it flies up from under the bar, grows, trails stacked red
  rim echoes, and flies through the silver MNF band with the replay already inside the letters. Seen before
  replays at obs 326/327, 359/360, 415/416, 448/449, 680/681, 719, 1251, 1574, 1670, 1702, 2349/2350, 2391/2392,
  2466, 2537/2538 and 2554, and mnf 87 and 96. The emblem median is p1's registration of mnf 87 and obs 327, 681,
  2350 and 2538.
- **Bumpers:** obs 830 (the MNF bumper: a red wall, chrome outline letters, white-hot edges), obs 1847/1848 (the
  emblem close-up going to break), obs 3099-3126 (the ESPN NFL open: red ribbons, 3D red ESPN letters, the NFL
  shield), mnf 9-12 (the Monday Night Kickoff banner).
- **Boards:** obs 1864-1868 (the corner score box: charcoal, white numerals), obs 3012-3016 (NEXT WEEK ON MNF),
  obs 3003-3008 (the postgame strip), obs 2587 (the team schedule board), and the 2026 bar itself (mnf 290-299).

Measured colours (RGB medians): emblem rim red 148, 10, 16 (63,138 pixels); wordmark red 191, 13, 19; plate black
10, 11, 16; MNF band silver 199, 200, 205; bumper wall red 120, 34, 37; bumper white-hot 242, 235, 232; ribbon red
234, 44, 53; board charcoal 32, 31, 32; board white 246, 245, 245; the bar's rim blue 42, 50, 122. The report
`reports/b76_p2/author_wipes_boards_report.json` holds every value with its 10th and 90th percentiles and source.

Retail layout was read from the resources for placement only (the glow letters' box, the crescent arc's centre and
radius, the RedFlashy quads, the lightning columns, the monitor's line and slit positions, the pause board's
triangles and the LED lattice): no retail texel is copied into the art.

### The pause board

The board's two atlases are drawn in display space and stored through the retail UV triangles: every texel is
sampled from the design at the display point its triangle maps it to, texels just outside a triangle take the
extrapolated design so bilinear filtering at a seam reads the design, and the tiny patch every silver frame samples
is set to the band silver directly. The LED labels keep their retail lattice cells (VISITOR, HOME, DOWN and the
possession marker on a 49 x 50 dot lattice) and are lettered with glyphs drawn for 2-dot strokes; W is M upside
down because the triangles draw DOWN's W from the M's dots. 364 LED dots show up in more than one place; each is lit
by the majority of its places (10 split votes).

What the board shows while the game is paused, and how its signs sit against the pause score and clock strip, is
**unwitnessed**: the research proved the scene is submitted as the game-active menu backdrop, not which widget
sits over which sign.

## Stays retail, with the reason in every receipt

| Target | Reason |
| --- | --- |
| logo_coin_wipe | no embedded texture (a 598-vertex logo mesh and a glow mesh) |
| fullscreen_PlayerOfTheGame_transition | its only descriptor is unbound |
| fullscreen_WipeRedName | a complete restyle (text, rings, a logo coin, team colours set at runtime) |
| enf_logo_wipe, snf_logo_wipe, overlay_wipe | no embedded texture |
| replay_wipe ESPN01/ESPN02 3D letters | untextured geometry coloured by material +0x18 (orange front, gold sides) |
| propsgamecoin (eight occurrences) | no coin toss in the 2026 frames (the unbound coin descriptors stay refused) |
| sc_studio, coach_desk, commish01 | no studio, desk or commissioner in the 2026 frames |
| bermanintro | read-only in this wave (the pregame intro freeze investigation) |
| sc_intro, playercard trim and Players Inc mark, menus, media, ticker, glowball, power meter | no broadcast counterpart in the 2026 frames |

The next lever toward the red 2026 letters of the replay transition is the material colour words (+0x18) of
`ESPN01_front`, `ESPN01_sides`, `ESPN02_front` and `ESPN02_sides`: fixed-size edits in the same raw MRKS, outside
this option's texture scope.

## Commands

    python3 -m mod_editor.core.nfl2k5_espn_wipes_boards status <image or extracted folder>
    python3 -m mod_editor.core.nfl2k5_espn_wipes_boards revert <image> --retail <retail image>
    python3 -m mod_editor.core.nfl2k5_espn_wipes_boards record-pins <retail source>          # author-time
    python3 reports/b76_p2/author_wipes_boards.py --frames <b76 frames> --packs <vc_53450030> --output <folder>
    python3 reports/b76_p2/render_preview.py --packs <vc_53450030>

Status is `retail`, `applied`, `mixed` or `foreign` across the six resources; only retail or already-2026 spans are
accepted. An outer that grew by chunks appended after a span still takes the option (the Guardian overlay appends
its helmet texture to GLOBAL.IFF, outer 3, which also holds the player card): every span keeps its offset and is
judged by its SHA-256, and the receipt gives each outer's size against retail. A span that moved or was cut reads as
foreign and nothing is written. The revert writes the six retail spans from a retail source, checked against their
pins; the repository holds only SHA-256 pins, never retail bytes.

## What to look at in game

1. An instant replay: the transition's flash, streaks, logo glow and rims in 2026 red and silver (the 3D ESPN
   letters keep their retail orange and gold).
2. Pause during a game: the scoreboard backdrop (marquee, emblem sign, LED labels, NFL shield, ESPN MNF lockup);
   say whether the pause score and clock sit where the board expects them.
3. The helmet bumper: the set monitor in MNF red with white outlines, and its scrolling red bands.
4. A player card: the current NFL shield.
5. Wherever RedFlashy or Electricity run (their callers are the wipe table's other rows): the red wordmark and the
   red bumper bolts.
