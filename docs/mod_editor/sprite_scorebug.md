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
  --aspect both --output /tmp/scorebug.png
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
or preview dependency. Noto attribution: Copyright 2015 Google Inc.

The layout uses source pixels on a 1920×1080 frame. `cells` name rectangles in
the PNG. `static` rows give a cell, frame box, depth (`z`) and tint (`none`,
`home team`, `away team`, `possessing team`). `fields` give their native data
source, glyph set, cap height (`size`), alignment, anchor, colour and slot count.
Glyphs name a cell, advance and optional raise. Width is compressed only when a
value exceeds its field box, allowing three-digit scores without overlap.

The default scene contains 45 quads: 11 static/logo quads, 30 glyph/tick slots,
and four retail event backgrounds. It uses 180 of 286 retail vertices. Material
push-buffer capacities still bound each group; the compiler refuses an overflow
before changing a game. A 512×512 atlas is accepted only if the complete append
still fits the 400 KiB ceiling; with the default logos it exceeds that ceiling.
The default 256×512 atlas plus 33 logos and enlarged scene appends 323,808 bytes.
Retail FONT resources stay byte-for-byte unchanged. FLAG, FUMBLE, hang time and
ball-on text use retail fonts and event callbacks. The rotating score slabs
conflict with sprite scores, so scores remain on the root while that event runs.
