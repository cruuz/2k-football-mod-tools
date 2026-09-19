# Sprite scorebug

The experimental sprite scorebug uses one `template.png` and one `layout.json`.
Copy `data/nfl2k5_scorebug_sprite` to make another design. Paint the PNG and edit
its JSON; compiling a supported design needs no font installation or code edit.
The supplied art keeps the light reflection along the top of the body.

On Scorebar Studio, choose **Preview**, select your game source and screenshot,
and set the teams, scores, clocks, downs and timeouts. **Use design in Build**
selects that folder and enables Scorebug and its experimental runtime option.
Both options remain off in every preset. Rebuild from the supported retail base.
The older page's layer editor produces the static scorebar format; sprite designs
use the separate PNG/JSON folder selected in Preview.

```sh
python3 -m mod_editor.core.nfl2k5_scorebug_sprite preview \
  --source '/path/to/your/ESPN NFL 2K5 (USA).xiso.iso' \
  --screenshot '/path/to/screenshot.png' \
  --state '{"away":"DEN","home":"KC","away_score":7,"home_score":7,"down":3,"distance":10,"quarter":2,"clock":273,"play_clock":4}' \
  --aspect both --output scorebug.png
```

`--pack` and `--xbe` accept an extracted game. Without either source option, the
command uses this checkout's `extracted/ESPN NFL 2K5 (USA)` directory. Outputs
include PNGs and JSON receipts. `goal_to_go: true` selects the native goal label;
`event` accepts `FLAG`, `FUMBLE`, `hang time`, `ball on`, `score slabs`, and
`hidden play clock`. Time is in seconds. Scores support 0–999.

The command executes the actual owner and native getters, then renders its live
vertex and UV streams through the same software raster used by `compare()`.
It does not boot the game. Both outputs use the game's 640×480 HUD coordinates;
16:9 includes its native 27/32 horizontal contraction. The screenshot is only a
background: an existing scorebug in it is not erased. The CPU/native-resource
proof does not establish console GPU appearance or intro memory behavior.

For a source installation, Preview requires Pillow, NumPy, Unicorn and Capstone
in addition to the Studio's PyQt5. The tested versions are recorded in
`tools/scorebug_sprite/requirements-preview.txt`; the Windows installer pins its
preview wheels by SHA-256. No dependency installation is needed to author a PNG.
No font file is shipped: the Noto Sans Display Bold glyphs were rendered once
under its SIL Open Font License 1.1, condensed and fitted to the specified sizes.
The one-time author script records the local source font path; it is not a build
or preview dependency. Noto attribution: Copyright 2015–2020 Google LLC.

The layout uses source pixels on a 1920×1080 frame. `cells` name rectangles in
the PNG. `static` rows give a cell, frame box, depth (`z`) and tint (`none`,
`home team`, `away team`, `possessing team`, `home rim`, `away rim`). `fields` give their native data
source, glyph set, cap height (`size`), alignment, anchor, colour and slot count.
Glyphs name a cell, advance and optional raise. Width is compressed only when a
value exceeds its field box, allowing three-digit scores without overlap.

The supplied layout declares `layer_order: "increasing-z"`: higher `z` draws
over lower `z` where their boxes overlap. Equal values follow declaration order
(static, brand, fields, events). Older layouts without that setting keep their
original decreasing-depth convention. Depth is a logical layer value; compiled
sprite vertices share one GPU depth. Material numbers are allocation preferences
for ordinary atlas layers; logo and event bindings remain fixed. The compiler
fits whole fields first, moves static plates when necessary, orders the scene's
draw descriptors and sorts quads inside each buffer. It refuses layouts that
cannot fit without reversing an overlap. Preview reads those actual descriptors
and buffers without using depth to correct their order.

Down glyph visibility follows the native element draw loop's binding and current
slide position. An event request is an input to an update, not a draw decision;
retail can request ball-on and down-and-distance together. The owner therefore
does not use event request words to erase the down glyphs. Events suppress them only while their own binding and slide gate is visible,
including fade-out, so translucent event pixels do not reveal underlying text.
Native transition tests verify this
behavior, but do not establish the cause of the persistent blank label reported
in a played game.

The default scene contains 47 quads: 12 static/logo quads, a watermark,
30 glyph/tick slots and four retail event backgrounds. It uses 188 of 286
retail vertices. A 512×512 atlas is accepted only if the complete append
still fits the 400,000-byte ceiling; with the default logos it exceeds that ceiling.
The default 256×512 atlas plus 33 logos and enlarged scene appends 323,808 bytes.
Retail FONT resources stay byte-for-byte unchanged. The FLAG label is baked into
its yellow plate; FUMBLE, hang time and ball-on text retain retail callbacks.
The rotating score slabs
conflict with sprite scores, so scores remain on the root while that event runs.

The beta 72 SD cut uses a 30 source pixel down cap, exceeding the dossier's
28 pixel proposal so the actual raster retains at least 12 ink scanlines. The
quarter and play-clock cap is 26 source pixels. Source metrics and cell texels
are separate: a label digit is 24 by 30 source pixels in an 8 by 12 texel cell.
Every atlas cell fits the smallest 16:9 footprint, including compressed
three-digit scores and two-digit-minute clocks. No mip is needed for these
cells. The separate retail-derived team-logo textures retain their existing
format and sampling model.

The opaque body uses one quad. Its former two end quads carry the team-coloured
wash and bottom rim, so the complete scene still uses 47 quads. Rim colours are
lighter derivatives of the live team tint. `wing_tints`, `plate_tints` and
`logo_fit` remain authored data. The plate carries lip, dip and sheen bands;
there is no label shadow. The capsule carries its separator inside the texture.
The pointer's rare feather colours and selected gloss and rim samples are
reserved in the P8 palette. White alpha masks keep the wing fades smooth.

`scorebug_watermark` is `auto`, `mnf` or `off`, saved with Build settings. Auto
selects ESPN NFL unless game mode is franchise, the current schedule record is
Monday, and the resolved time-of-day enum is night. The owner calls the current
record weekday site at `0xD22AC`, which the extended calendar detours. It never
bypasses that detour with a direct call to the historical date routine.
Out-of-range weeks/slots and empty or out-of-range month/day fields select NFL.

Two brand rows with `variant: "nfl"` and `variant: "mnf"` share one placement,
opacity, material and depth. Only one quad is allocated. Its static record
points to immutable NFL/MNF UVs and a policy word in the appended scene.
The NFL face reuses the measured ESPN, N and F cells; its L is made from the
F stem and flipped top arm. A separate ESPN NFL still was unavailable, so
this reconstruction's provenance is recorded in the layout.
The selector controls this paired variant group. Untagged brand rows in custom
designs retain their existing static artwork.

Preview's `broadcast` state accepts `play_now`, `monday_night`, `sunday_night`
and `monday_afternoon`; `--watermark` selects the policy. These states populate
bounded synthetic schedule records and execute the real weekday site. The GUI
shows the final display image, after native contraction and viewport expansion.

Run the measurement tool with your read-only broadcast reference directory:

```sh
python3 tools/scorebug_sprite/match_espn.py --frames /path/to/frames --output reports/b72_s1
```

The default residual limits are 1 HUD pixel and 6 RGB units. Static colours use
the dossier's temporal median, with the canonical frame for possession-dependent
regions, projected to the same SD footprint before display expansion. Original
source RGB is retained in JSON. The larger SD type is an explicit exception to
1080-line text proportions. Minimum readability gates have zero tolerance.
The 16 representative frames are measured separately from the canonical frame;
scoring overlays and moving reflections are not treated as standard label ink.

The default remains 323,808 appended bytes, a zero-byte change from beta 71.1,
against a 400,000 byte ceiling. The code owner remains 4,096 bytes. Native CPU
execution, software rasterization and bounded state fixtures do not establish
console GPU appearance or played-game behaviour. Everything in game remains
UNWITNESSED.
