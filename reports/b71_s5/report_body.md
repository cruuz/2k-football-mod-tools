# Beta 71 S5 — sprite scorebug

S5 replaces the bar's presentation with **one PNG + one JSON**, compiled into a
256×512 P8 atlas and 45 preallocated quads. The bar emits **zero FONT glyphs**.
The native loader accepts an enlarged same-name `score_bug` SCNE and returns it
from the HUD lookup. The proved logo resources, native getters and owner hooks
remain. The top reflection is painted into the body. The option is off in every
preset. **Played-game behavior, console GPU appearance and the intro are
UNWITNESSED.** No xemu session, disc build or push was performed.

The private branch `astra/b71-s5-sprite-scorebug` starts at integrated HEAD
`cea8a3c8`. Git metadata is in `.scratch/b71-s5-git`; the shared worktree `.git`
was read only. Commits use explicit paths. The delivery bundle is
`.scratch/astra-b71-s5.bundle` with `cea8a3c8` as its prerequisite.

The S5 request expressly authorizes the scorebug owner, Studio wiring, allocator,
packaging, registry and cave projection changes that the older generic
`ASTRA_CONTEXT.md` reserves. S3/S4 and the corrected triage measurements were
read. The retained shine was checked against
`beta71_evidence/disc_i_scorebug_v3_shine_1.png`; the native preview also has a
real day-game screenshot as its background.

## Authoring and route proofs

- **Authoring:** `data/nfl2k5_scorebug_sprite/template.png` and `layout.json` are
  the product inputs. `mod_editor/core/nfl2k5_scorebug_sprite.py:41` validates
  the format; `:94` packs cells deterministically with transparent RGB gutters;
  `:135` emits the field/glyph/static tables. Every field has source, glyph set,
  size, alignment, anchor, colour and slots. Boxes use the 1920×1080 reference
  frame. A future compatible design changes those two files only.
- **Glyphs:** `tools/scorebug_sprite/author_default.py:48` renders bold Noto Sans
  Display outlines once, condensed and fitted at score 40×53, clock 23×27,
  small 15×19, and down-label 16×23. The sheet contains digits, colon, ticks,
  ordinals, ampersand, Goal/GOAL, and, OT and Inches. Full alpha survives in the
  authored sheet. Noto uses OFL 1.1; no font file is shipped or needed to build.
- **Scene:** `nfl2k5_scorebug_sprite.py:178` preserves native stream/pointer
  offsets and the 286-vertex allocation, writes static quads and push buffers,
  then adds its immutable layout table at decoded offset 16,512. The resource
  header's spare words at +0x60 carry SPR5 and that offset. It checks those
  words before using them. Quads use 180 vertices; 11 existing material groups
  and their command capacities remain bounded. There are 11 static/logo quads,
  30 glyph/tick slots and four retail event backgrounds.
- **Larger same-name SCNE is PROVED:** `reports/b71_s5/probe_scene.py` and
  `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:120` execute the actual native
  collection reader `0x43A20`, SCNE handler `0x45A90`, relocation/registration
  and typed lookup `0x449E0`. Retail decoded SCNE is 16,512 bytes; the independent
  route probe appends 24,704 decoded bytes and the newer object wins. The final
  resource probe loads the actual 20,384-byte SCNE chunk alongside 34 TXTRs and
  no FONT. Thus the old compressed 4,800-byte span is not the limiting route.
  Boundary substitutions are OS I/O completions and startup animation; no
  loader return value or resource lookup is substituted. See `scene-route.json`.
- **Runtime:** `mod_editor/core/nfl2k5_scorebug_runtime.py:346` dispatches only a
  SPR5 scene to the new engine, retaining the historical ABI for explicit old
  diagnostic profiles. It calls the displaced native setup/update once and
  wraps the new engine with GPR/flags and FXSAVE/FXRSTOR preservation.
  `tools/scorebug_sprite/runtime.c:50` resolves per-team logo textures, installs
  empty bar callbacks and retains retail FONT descriptor/slot words. `:71`
  calls the existing score, clock, quarter, down/distance and play-clock
  formatters. Timeout counts come from the same native score objects. `:85`
  selects glyph cells, packs/aligns values, writes UVs/positions/colour and
  hides unused quads. `:122` updates wing and possession-plate tints from the
  existing team colour metadata. The generated instructions are shipped as
  `nfl2k5_scorebug_sprite_code.py`; gcc is not a product dependency.
- **Cave:** RX grows from 1,408 to 4,096 bytes (3,529 used); RW stays 128 bytes. The allocator
  at `mod_editor/core/nfl2k5_xbe_space.py:657` preserves the historical footprint
  while packing other owners, then places the larger owner after the existing
  RX union. No unrelated owner moves. The old absolute-code regression control
  executes at its original, unused RX span; the new owner is checked separately.
- **Build:** `nfl2k5_scorebug_ingame.py:845` defaults the runtime plan to `sprite`,
  validates optional design folders, and preserves transactional pack/XBE
  rollback. `nfl2k5_scorebug_resources.py:798` dispatches to the sprite compiler.
  `mod_editor/core/mod_build.py:1239` validates the folder; `:1941` forwards it. The runtime CLI
  defaults to sprites; old diagnostic profiles require explicit selection.
- **Preview:** `nfl2k5_scorebug_sprite.py:306` reads a retail ISO or extracted
  game, executes the owner and native getters, and captures its live streams.
  `tools/nfl2k5_scorebug_projection.py:728` is the shared depth/alpha/bilinear
  software raster used by `compare()`. No parallel text renderer estimates the
  bar. `mod_editor/gui/scorebug_studio_panel_qt.py:916` opens the new dialog;
  `scorebug_sprite_preview_qt.py` runs the real command in a QProcess, and
  `studio_qt.py:8963` carries its selected design into Build.

The Studio process was tested offscreen against the actual retail ISO. A second
native design proof changed the score anchor by six source pixels, its size to
40 and its colour to #FFAA22, with **identical owner code**. Native centre and
height followed the JSON; see `custom-design.json`.
The real page's Preview button was clicked and the completed dialog captured in
[studio-preview.png](reports/b71_s5/studio-preview.png). It scrolls to the bar
automatically; the selected PNG/JSON folder is validated before Build handoff.

## Layout and volume

The source bar is [437,942,1478,1052]. Wings end at 650 and start at 1265; the
plate is [837,947,1083,983] with its pointer reaching y942. Housing is
[837,983,1083,1045], white capsule [839,999,1019,1039], red cell
[1019,999,1082,1040]. The standard score glyphs are 40×53 at y965; clocks,
quarter and down boxes are serialized in `layout.json`, not authored in the
runtime. Ticks are 20×6 with 10-pixel gaps. HUD conversion is x/3 and
16+y×448/1080; 16:9 contracts x by 27/32 about 320.

| Appended component | Count | Bytes each | Total bytes |
| --- | ---: | ---: | ---: |
| Team logo TXTR | 32 | 5,280 | 168,960 |
| Neutral fallback TXTR | 1 | 2,208 | 2,208 |
| `score_buga` P8 256×512 TXTR | 1 | 132,256 | 132,256 |
| Enlarged `score_bug` SCNE + layout | 1 | 20,384 | 20,384 |
| FONT | 0 | 0 | 0 |
| **Total append** | **35 resources** | | **323,808** |

The native heap-rounded component sum is 327,168 bytes. Sector-aligned pack growth is 323,584 bytes, using the old trailing sector slack. The append is below
both 400,000 bytes and the compiler's 400 KiB ceiling. A deliberately enlarged
512×512 profile is refused by that ceiling. A bigger atlas is only usable with
another supported resource budget; it cannot bypass the total-volume check.
The retail HUD and global FONT resources remain byte-identical. All component
hashes and counts are in `reports/b71_s5/volume.json`. This is a freeze-class
volume bound, **not** a played intro peak-memory witness.

## Previews and measured proof

- [Standard 4:3, ESPN above / native below at 2×](reports/b71_s5/standard_43_compare_2x.png)
- [Standard 16:9, ESPN above / native below at 2×](reports/b71_s5/standard_169_compare_2x.png)
- [NO at DEN, near-black possession plate](reports/b71_s5/no_at_den_169_compare_2x.png)
- [All 50 state/aspect crops](reports/b71_s5/states_contact_sheet.png)
- [Real day-game background, 4:3](reports/b71_s5/day_43.png) and [16:9](reports/b71_s5/day_169.png)
- [The actual appended P8 atlas, decoded to PNG](reports/b71_s5/atlas.png)

The individual `*_compare_2x.png` files cover the standard DEN/KC 7–7,
3rd & 10, 2nd 4:33, play-clock 4 state; NO/DEN; 0, 28 and 100 scores;
0:07; play clocks 12 and 3; every down; OT; Inches and Goal; timeouts 3 through
0; and FLAG, FUMBLE, hang time, ball on, score slabs and hidden play clock.

Standard static boundaries are within 0.007 HUD px. Standard dynamic boundaries
are within 0.167 HUD px and measured visible glyph ink within 0.830 HUD px at
both aspects. Every visible field in all 50 captures stays inside its authored
box within 0.007 HUD px. The raster is deliberately shown at native resolution
before enlargement. The two-times comparison shows both the design differences
and the game's sampling limit; **it is not a pixel-identical ESPN photograph**.
The legacy RGB comparison remains a mismatch. `measurements.json` retains those
results rather than substituting a layout-only success for an image match.

The background screenshot is not erased or retouched. If it contains an earlier
scorebug, any uncovered pixels remain visible. The preview uses explicit game
state and world-query boundary values; it does not predict a later played
match's state. Native 640×480 HUD coordinates are used in both files, including
the 16:9 contraction. Console GPU sampling and full display scaling remain
UNWITNESSED.

Visual review found that sampling the edges of the body's single-texel atlas
strip blended its transparent gutter across the stretched quad. The compiler
now samples a one-texel strip at its centre. A native black/white-background
test proves the bar interior, translucent wings and logo cutouts differ by no
more than one RGB level at both aspects. The final previews include that fix;
earlier render logs remain in the command ledger.

Retail event treatment is explicit: FLAG, FUMBLE, hang time and ball-on retain
the native event callbacks and retail font path, replacing down text while
leaving the clock capsule readable. Rotating score slabs conflict with sprite
scores, so the score glyphs remain attached to the root while that event runs;
the old rotating score backgrounds are not reused. The owner produces zero
FONT glyphs for all ordinary bar fields. Event draws are recorded individually
in `states.json`.

`owner-bounds.json` records 166 setup and 2,282 update writes, with zero writes
outside the named RW state, stack, scene streams/materials and exact callback
words. GPRs, flags, x87 state, MXCSR and XMM registers survive both hooks;
displaced calls run exactly once. Native tests also cover scene replacement,
team binding/secondary plate colour, repeated updates, unused-slot hiding,
reapplication, foreign code/data/resource refusal and unchanged retail HUD.

## Integration and delivery status

Provider import closure adds seven modules and pins 295 module identities.
Release packaging includes the PNG/JSON, renderer dependencies and preview
entry point. The Windows wheel list has exact SHA-256 pins from the official
[NumPy 1.26.4 files](https://pypi.org/project/numpy/1.26.4/#files) and
[Unicorn 2.1.4 files](https://pypi.org/project/unicorn/2.1.4/#files).
Those metadata reads did not install dependencies; Windows execution is
UNWITNESSED. Linux native preview and offscreen Studio execution are proved.
The strict registry validator passes with its file checks enabled. Its 75 inherited ignored evidence files were restored from the prior hash inventory as independent copies (2,063,157 bytes); those private inputs are not committed or bundled. The validation plan remains 176 rows, 171 covered, five deferred and 129 unique commands. The existing registry row and RC96 bullet describe sprites and preserve the
experimental, off-by-default status.
The unfinished RC96 scorebug paragraphs for earlier FONT-based designs were
consolidated into the S5 bullet, avoiding contradictory current resource counts.
Their S3/S4 reports and earlier commits remain available.

`reports/b71_s5/build_testdisc71.py` is prepared from the A6/A7 builder pattern.
Its plan names **NFL 2K5 MOD TEST 2026-09-15m (sprite scorebug + everything)**,
uses `softdrink_advanced`, and enables scorebug, scorebug_runtime, modern colour,
modern Arrowhead and widescreen. `verify_builder.py` inspects that plan without
calling the builder. The builds directory is untouched. `prepared-builder.json`
records `builder_run: false` and `disc_built: false`.

The regenerated cave document is an explicitly labelled bounded XBE projection,
not a release disc manifest. Historical disc fields remain historical; full
production regeneration is still required when the integrating owner builds a
disc. The final gate/command results follow below.

The final projection seals 339 current source files. Its stack XBE SHA-256 is
`472862f4eac5420137f97529fe3c27b5f000f0ab6a005bd1d8a14d46c753bd60`.
`projection-identity.json` proves that executable and its allocator layout are
identical before and after the atlas sampling correction, so both XBE gates
cover the final owner bytes. The first oracle run overlapped that resource-only
edit and correctly refused the stale compiler seal; its subsequent run uses
the regenerated projection. The manifest remains below the 8 MiB reader bound.

The final commit, bundle hash, size and independent fetch verification are
recorded in `.scratch/b71-s5-delivery.json`. The report's command ledger records
the development checks; that delivery receipt records the final explicit-path
commit and bundle commands with their timing and exit codes.

The 16 explicit suite skips are retained: six legacy layout checks depend on
the old Create-a-Play image, opt-in legacy emulation or an intermediate glTF;
three source-art checks need absent developer exports/audit inputs; five test
the retired beta-69 private-font owner; one full-disc transaction cannot create
scratch on the read-only storage volume; and one XBE-space check tests a retired
kickoff mechanism. The S5 native loader, owner, raster and Studio checks have
no skips. No full disc was copied to bypass the storage restriction.
