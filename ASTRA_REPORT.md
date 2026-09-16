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

## Completed verification results

The table below contains the latest completed run of each test/validator command. A pending gate is not counted as passed.

Required suites: 40. Latest completed results: 1160 tests, 16 explicit skips. Missing required results: none. Failed latest results: none.

| Check | Tests | Skips | Seconds | Exit |
| --- | ---: | ---: | ---: | ---: |
| [allocator-final](reports/b71_s5/allocator-final.log) | 23 | 0 | 821.732 | 0 |
| [corrected-test_nfl2k5_scorebug_freeze_v2](reports/b71_s5/corrected-test_nfl2k5_scorebug_freeze_v2.log) | 7 | 0 | 341.322 | 0 |
| [corrected-test_nfl2k5_scorebug_resources](reports/b71_s5/corrected-test_nfl2k5_scorebug_resources.log) | 6 | 0 | 374.772 | 0 |
| [final-nfl2k5_scorebug_layout_test](reports/b71_s5/final-nfl2k5_scorebug_layout_test.log) | 15 | 6 | 1.465 | 0 |
| [final-nfl2k5_scorebug_mod_project_test](reports/b71_s5/final-nfl2k5_scorebug_mod_project_test.log) | 10 | 0 | 1.361 | 0 |
| [final-test_apf_scorebug_workspace_qt](reports/b71_s5/final-test_apf_scorebug_workspace_qt.log) | 11 | 0 | 1.417 | 0 |
| [final-test_build_panel_qt](reports/b71_s5/final-test_build_panel_qt.log) | 13 | 0 | 2.874 | 0 |
| [final-test_mod_build](reports/b71_s5/final-test_mod_build.log) | 13 | 0 | 1.867 | 0 |
| [final-test_nfl2k5_scorebar_rim](reports/b71_s5/final-test_nfl2k5_scorebar_rim.log) | 8 | 0 | 14.382 | 0 |
| [final-test_nfl2k5_scorebar_v3](reports/b71_s5/final-test_nfl2k5_scorebar_v3.log) | 9 | 0 | 104.825 | 0 |
| [final-test_nfl2k5_scorebug_assets](reports/b71_s5/final-test_nfl2k5_scorebug_assets.log) | 8 | 1 | 151.668 | 0 |
| [final-test_nfl2k5_scorebug_author](reports/b71_s5/final-test_nfl2k5_scorebug_author.log) | 12 | 0 | 6.712 | 0 |
| [final-test_nfl2k5_scorebug_fonts](reports/b71_s5/final-test_nfl2k5_scorebug_fonts.log) | 10 | 5 | 9.467 | 0 |
| [final-test_nfl2k5_scorebug_freeze](reports/b71_s5/final-test_nfl2k5_scorebug_freeze.log) | 7 | 0 | 249.322 | 0 |
| [final-test_nfl2k5_scorebug_ingame](reports/b71_s5/final-test_nfl2k5_scorebug_ingame.log) | 11 | 0 | 15.675 | 0 |
| [final-test_nfl2k5_scorebug_ingame_fix](reports/b71_s5/final-test_nfl2k5_scorebug_ingame_fix.log) | 9 | 0 | 131.437 | 0 |
| [final-test_nfl2k5_scorebug_mnf](reports/b71_s5/final-test_nfl2k5_scorebug_mnf.log) | 10 | 0 | 12.543 | 0 |
| [final-test_nfl2k5_scorebug_mnf_v3](reports/b71_s5/final-test_nfl2k5_scorebug_mnf_v3.log) | 7 | 0 | 51.821 | 0 |
| [final-test_nfl2k5_scorebug_native](reports/b71_s5/final-test_nfl2k5_scorebug_native.log) | 4 | 0 | 134.934 | 0 |
| [final-test_nfl2k5_scorebug_projection](reports/b71_s5/final-test_nfl2k5_scorebug_projection.log) | 14 | 0 | 57.724 | 0 |
| [final-test_nfl2k5_scorebug_runtime](reports/b71_s5/final-test_nfl2k5_scorebug_runtime.log) | 12 | 0 | 121.592 | 0 |
| [final-test_nfl2k5_scorebug_source_art](reports/b71_s5/final-test_nfl2k5_scorebug_source_art.log) | 13 | 3 | 0.465 | 0 |
| [final-test_nfl2k5_scorebug_template](reports/b71_s5/final-test_nfl2k5_scorebug_template.log) | 19 | 0 | 10.024 | 0 |
| [final-test_nfl2k5_scorebug_unified_adapter](reports/b71_s5/final-test_nfl2k5_scorebug_unified_adapter.log) | 5 | 0 | 0.18 | 0 |
| [final-test_nfl2k5_scorebug_v10_ingame](reports/b71_s5/final-test_nfl2k5_scorebug_v10_ingame.log) | 11 | 0 | 9.297 | 0 |
| [final-test_nfl2k5_scorebug_v10_projection](reports/b71_s5/final-test_nfl2k5_scorebug_v10_projection.log) | 14 | 0 | 30.042 | 0 |
| [final-test_nfl2k5_scorebug_versions](reports/b71_s5/final-test_nfl2k5_scorebug_versions.log) | 4 | 0 | 9.836 | 0 |
| [final-test_nfl2k5_xbe_space](reports/b71_s5/final-test_nfl2k5_xbe_space.log) | 13 | 1 | 35.225 | 0 |
| [final-test_scorebug_studio_panel_qt](reports/b71_s5/final-test_scorebug_studio_panel_qt.log) | 11 | 0 | 7.496 | 0 |
| [gate-test_nfl2k5_owner_pairwise_composition](reports/b71_s5/gate-test_nfl2k5_owner_pairwise_composition.log) | 506 | 0 | 2966.963 | 0 |
| [gate-test_xbe_patch_cave_references](reports/b71_s5/gate-test_xbe_patch_cave_references.log) | 131 | 0 | 1752.922 | 0 |
| [gate-test_xbe_patch_memory_writes](reports/b71_s5/gate-test_xbe_patch_memory_writes.log) | 119 | 0 | 1558.063 | 0 |
| [opacity-release-test_phase1_packaging](reports/b71_s5/opacity-release-test_phase1_packaging.log) | 23 | 0 | 2.219 | 0 |
| [opacity-release-test_product_catalog](reports/b71_s5/opacity-release-test_product_catalog.log) | 9 | 0 | 0.155 | 0 |
| [opacity-release-test_provider_integrity](reports/b71_s5/opacity-release-test_provider_integrity.log) | 8 | 0 | 10.988 | 0 |
| [opacity-release-test_scorebug_sprite_preview_qt](reports/b71_s5/opacity-release-test_scorebug_sprite_preview_qt.log) | 2 | 0 | 12.87 | 0 |
| [opacity-tests](reports/b71_s5/opacity-tests.log) | 11 | 0 | 97.035 | 0 |
| [oracle-current](reports/b71_s5/oracle-current.log) | 29 | 0 | 360.839 | 0 |
| [registry-current](reports/b71_s5/registry-current.log) | — | 0 | 0.157 | 0 |
| [revised-test_nfl2k5_scorebug_exact](reports/b71_s5/revised-test_nfl2k5_scorebug_exact.log) | 8 | 0 | 100.941 | 0 |
| [shipping-test_nfl2k5_scorebug_template_release](reports/b71_s5/shipping-test_nfl2k5_scorebug_template_release.log) | 5 | 0 | 0.561 | 0 |
| [validators-plan](reports/b71_s5/validators-plan.log) | — | 0 | 0.289 | 0 |

## Exact command ledger

Every detached verification, render, authoring, compiler and repin command run through `run_logged.py` is retained below, including failed and superseded attempts. Times are UTC; seconds are elapsed wall time. Short read-only source inspections were not benchmark runs. Heavy launch form was `setsid nohup python3 reports/b71_s5/run_logged.py NAME COMMAND ... > reports/b71_s5/NAME.launch.log 2>&1 < /dev/null & wait $!`, with log polling. Batch runners use the same recorder for each command.

| Run / log | Start UTC | Seconds | Exit | Exact argv |
| --- | --- | ---: | ---: | --- |
| [scene-probe](reports/b71_s5/scene-probe.log) | 2026-09-16T01:57:58.721102+00:00 | 19.239 | 1 | `python3 reports/b71_s5/probe_scene.py` |
| [scene-probe-fixed](reports/b71_s5/scene-probe-fixed.log) | 2026-09-16T01:58:34.153831+00:00 | 19.155 | 0 | `python3 reports/b71_s5/probe_scene.py` |
| [author-default](reports/b71_s5/author-default.log) | 2026-09-16T02:01:03.580037+00:00 | 0.294 | 0 | `python3 tools/scorebug_sprite/author_default.py` |
| [compiler-first](reports/b71_s5/compiler-first.log) | 2026-09-16T02:04:31.868493+00:00 | 0.294 | 0 | `python3 -c 'from mod_editor.core.nfl2k5_scorebug_sprite import *; c=compile_folder(); print(len(c.quads),len(c.table),probe_sizes()); c.atlas.save("reports/b71_s5/atlas.png")'` |
| [build-engine](reports/b71_s5/build-engine.log) | 2026-09-16T02:06:33.517633+00:00 | 0.207 | 1 | `python3 tools/scorebug_sprite/build_runtime.py` |
| [author-refined](reports/b71_s5/author-refined.log) | 2026-09-16T02:06:33.760729+00:00 | 0.266 | 0 | `python3 tools/scorebug_sprite/author_default.py` |
| [build-engine-fixed](reports/b71_s5/build-engine-fixed.log) | 2026-09-16T02:07:13.120829+00:00 | 0.211 | 1 | `python3 tools/scorebug_sprite/build_runtime.py` |
| [build-engine-no-rodata](reports/b71_s5/build-engine-no-rodata.log) | 2026-09-16T02:07:32.797817+00:00 | 0.165 | 1 | `python3 tools/scorebug_sprite/build_runtime.py` |
| [build-engine-aliasing](reports/b71_s5/build-engine-aliasing.log) | 2026-09-16T02:08:07.295102+00:00 | 0.106 | 0 | `python3 tools/scorebug_sprite/build_runtime.py` |
| [owner-first](reports/b71_s5/owner-first.log) | 2026-09-16T02:08:31.985694+00:00 | 3.107 | 0 | `python3 -c 'from pathlib import Path; from mod_editor.core import nfl2k5_scorebug_runtime as r; p=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe").read_bytes(); q,rec=r.apply(p); print(r.status(q),r.sites(q),r.code_for(*[v["va"] for v in r.sites(q)])[1]); print(r.apply(q)[1])'` |
| [preview-first](reports/b71_s5/preview-first.log) | 2026-09-16T02:09:42.645429+00:00 | 13.102 | 0 | `python3 -m mod_editor.core.nfl2k5_scorebug_sprite preview --screenshot /home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg --aspect 4:3 --output reports/b71_s5/first.png` |
| [build-engine-materials](reports/b71_s5/build-engine-materials.log) | 2026-09-16T02:11:17.453043+00:00 | 0.111 | 0 | `python3 tools/scorebug_sprite/build_runtime.py` |
| [preview-materials](reports/b71_s5/preview-materials.log) | 2026-09-16T02:11:17.595210+00:00 | 12.146 | 0 | `python3 -m mod_editor.core.nfl2k5_scorebug_sprite preview --screenshot /home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg --aspect 4:3 --output reports/b71_s5/second.png` |
| [sprite-tests-first](reports/b71_s5/sprite-tests-first.log) | 2026-09-16T02:14:19.622802+00:00 | 81.22 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` |
| [sprite-tests-revised](reports/b71_s5/sprite-tests-revised.log) | 2026-09-16T02:19:10.769541+00:00 | 88.075 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` |
| [early-test_nfl2k5_scorebug_runtime](reports/b71_s5/early-test_nfl2k5_scorebug_runtime.log) | 2026-09-16T02:21:00.554070+00:00 | 119.079 | 1 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py -v` |
| [early-test_nfl2k5_xbe_space](reports/b71_s5/early-test_nfl2k5_xbe_space.log) | 2026-09-16T02:21:00.554586+00:00 | 28.905 | 1 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_xbe_space.py -v` |
| [early-test_nfl2k5_allocator_scaleout](reports/b71_s5/early-test_nfl2k5_allocator_scaleout.log) | 2026-09-16T02:21:00.555389+00:00 | 439.112 | 1 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py -v` |
| [early-test_mod_build](reports/b71_s5/early-test_mod_build.log) | 2026-09-16T02:21:29.460153+00:00 | 2.256 | 0 | `/usr/bin/python3 tests/mod_editor/test_mod_build.py -v` |
| [early-test_build_panel_qt](reports/b71_s5/early-test_build_panel_qt.log) | 2026-09-16T02:21:31.716740+00:00 | 3.414 | 0 | `/usr/bin/python3 tests/mod_editor/test_build_panel_qt.py -v` |
| [early-test_scorebug_studio_panel_qt](reports/b71_s5/early-test_scorebug_studio_panel_qt.log) | 2026-09-16T02:21:35.130779+00:00 | 7.806 | 0 | `/usr/bin/python3 tests/mod_editor/test_scorebug_studio_panel_qt.py -v` |
| [author-data-layers](reports/b71_s5/author-data-layers.log) | 2026-09-16T02:22:49.584333+00:00 | 0.283 | 0 | `python3 tools/scorebug_sprite/author_default.py` |
| [preview-matrix](reports/b71_s5/preview-matrix.log) | 2026-09-16T02:24:20.717565+00:00 | 164.667 | 0 | `python3 reports/b71_s5/prove_previews.py` |
| [revised-runtime](reports/b71_s5/revised-runtime.log) | 2026-09-16T02:29:34.058643+00:00 | 120.432 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py -v` |
| [gui-native](reports/b71_s5/gui-native.log) | 2026-09-16T02:33:53.850847+00:00 | 12.504 | 0 | `python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` |
| [preview-final](reports/b71_s5/preview-final.log) | 2026-09-16T02:33:54.975377+00:00 | 171.937 | 0 | `python3 reports/b71_s5/prove_previews.py` |
| [repin-initial](reports/b71_s5/repin-initial.log) | 2026-09-16T02:33:56.145005+00:00 | 22.0 | 0 | `python3 packaging/repin.py --apply` |
| [manifest-projection](reports/b71_s5/manifest-projection.log) | 2026-09-16T02:34:38.416893+00:00 | 340.951 | 1 | `python3 reports/b71_s5/refresh_manifest_projection.py` |
| [final-test_apf_scorebug_workspace_qt](reports/b71_s5/final-test_apf_scorebug_workspace_qt.log) | 2026-09-16T02:35:05.334521+00:00 | 1.417 | 0 | `python3 tests/mod_editor/test_apf_scorebug_workspace_qt.py -v` |
| [final-test_nfl2k5_scorebar_rim](reports/b71_s5/final-test_nfl2k5_scorebar_rim.log) | 2026-09-16T02:35:05.335010+00:00 | 14.382 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_rim.py -v` |
| [final-test_nfl2k5_scorebar_v3](reports/b71_s5/final-test_nfl2k5_scorebar_v3.log) | 2026-09-16T02:35:05.335443+00:00 | 104.825 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_v3.py -v` |
| [final-test_nfl2k5_scorebug_assets](reports/b71_s5/final-test_nfl2k5_scorebug_assets.log) | 2026-09-16T02:35:06.751790+00:00 | 151.668 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_assets.py -v` |
| [final-test_nfl2k5_scorebug_author](reports/b71_s5/final-test_nfl2k5_scorebug_author.log) | 2026-09-16T02:35:19.717364+00:00 | 6.712 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_author.py -v` |
| [final-test_nfl2k5_scorebug_exact](reports/b71_s5/final-test_nfl2k5_scorebug_exact.log) | 2026-09-16T02:35:26.429954+00:00 | 99.525 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` |
| [owner-bounds](reports/b71_s5/owner-bounds.log) | 2026-09-16T02:36:47.562388+00:00 | 20.624 | 0 | `python3 reports/b71_s5/prove_owner_bounds.py` |
| [final-test_nfl2k5_scorebug_fonts](reports/b71_s5/final-test_nfl2k5_scorebug_fonts.log) | 2026-09-16T02:36:50.160640+00:00 | 9.467 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_fonts.py -v` |
| [final-test_nfl2k5_scorebug_freeze](reports/b71_s5/final-test_nfl2k5_scorebug_freeze.log) | 2026-09-16T02:36:59.628175+00:00 | 249.322 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py -v` |
| [final-test_nfl2k5_scorebug_freeze_v2](reports/b71_s5/final-test_nfl2k5_scorebug_freeze_v2.log) | 2026-09-16T02:37:05.955184+00:00 | 343.728 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` |
| [prepared-builder](reports/b71_s5/prepared-builder.log) | 2026-09-16T02:37:30.527462+00:00 | 0.246 | 0 | `python3 reports/b71_s5/verify_builder.py` |
| [final-test_nfl2k5_scorebug_ingame](reports/b71_s5/final-test_nfl2k5_scorebug_ingame.log) | 2026-09-16T02:37:38.419863+00:00 | 15.675 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame.py -v` |
| [final-test_nfl2k5_scorebug_ingame_fix](reports/b71_s5/final-test_nfl2k5_scorebug_ingame_fix.log) | 2026-09-16T02:37:54.094734+00:00 | 131.437 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py -v` |
| [repin-final-source](reports/b71_s5/repin-final-source.log) | 2026-09-16T02:40:04.765006+00:00 | 23.356 | 0 | `python3 packaging/repin.py --apply` |
| [final-test_nfl2k5_scorebug_mnf](reports/b71_s5/final-test_nfl2k5_scorebug_mnf.log) | 2026-09-16T02:40:05.531740+00:00 | 12.543 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf.py -v` |
| [final-test_nfl2k5_scorebug_mnf_v3](reports/b71_s5/final-test_nfl2k5_scorebug_mnf_v3.log) | 2026-09-16T02:40:18.074853+00:00 | 51.821 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py -v` |
| [manifest-final](reports/b71_s5/manifest-final.log) | 2026-09-16T02:41:05.283142+00:00 | 337.728 | 0 | `python3 reports/b71_s5/refresh_manifest_projection.py` |
| [revised-test_nfl2k5_scorebug_exact](reports/b71_s5/revised-test_nfl2k5_scorebug_exact.log) | 2026-09-16T02:41:06.342722+00:00 | 100.941 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` |
| [revised-test_nfl2k5_scorebug_freeze_v2](reports/b71_s5/revised-test_nfl2k5_scorebug_freeze_v2.log) | 2026-09-16T02:41:06.343512+00:00 | 333.849 | 1 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` |
| [final-test_nfl2k5_scorebug_native](reports/b71_s5/final-test_nfl2k5_scorebug_native.log) | 2026-09-16T02:41:08.950639+00:00 | 134.934 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_native.py -v` |
| [final-test_nfl2k5_scorebug_projection](reports/b71_s5/final-test_nfl2k5_scorebug_projection.log) | 2026-09-16T02:41:09.895960+00:00 | 57.724 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_projection.py -v` |
| [final-test_nfl2k5_scorebug_resources](reports/b71_s5/final-test_nfl2k5_scorebug_resources.log) | 2026-09-16T02:42:07.620519+00:00 | 333.39 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py -v` |
| [final-test_nfl2k5_scorebug_runtime](reports/b71_s5/final-test_nfl2k5_scorebug_runtime.log) | 2026-09-16T02:42:49.683494+00:00 | 121.592 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py -v` |
| [final-test_nfl2k5_scorebug_source_art](reports/b71_s5/final-test_nfl2k5_scorebug_source_art.log) | 2026-09-16T02:43:23.885148+00:00 | 0.465 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_source_art.py -v` |
| [final-test_nfl2k5_scorebug_sprite](reports/b71_s5/final-test_nfl2k5_scorebug_sprite.log) | 2026-09-16T02:43:24.350448+00:00 | 88.477 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` |
| [custom-design](reports/b71_s5/custom-design.log) | 2026-09-16T02:43:36.595550+00:00 | 11.046 | 0 | `python3 reports/b71_s5/prove_custom_design.py` |
| [final-test_nfl2k5_scorebug_template](reports/b71_s5/final-test_nfl2k5_scorebug_template.log) | 2026-09-16T02:44:51.275972+00:00 | 10.024 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template.py -v` |
| [final-test_nfl2k5_scorebug_template_release](reports/b71_s5/final-test_nfl2k5_scorebug_template_release.log) | 2026-09-16T02:44:52.827941+00:00 | 0.475 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py -v` |
| [final-test_nfl2k5_scorebug_unified_adapter](reports/b71_s5/final-test_nfl2k5_scorebug_unified_adapter.log) | 2026-09-16T02:44:53.303343+00:00 | 0.18 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py -v` |
| [final-test_nfl2k5_scorebug_v10_ingame](reports/b71_s5/final-test_nfl2k5_scorebug_v10_ingame.log) | 2026-09-16T02:44:53.483966+00:00 | 9.297 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py -v` |
| [release-test_provider_integrity](reports/b71_s5/release-test_provider_integrity.log) | 2026-09-16T02:45:00.718084+00:00 | 0.224 | 5 | `/usr/bin/python3 tests/mod_editor/test_provider_integrity.py -v` |
| [release-test_product_catalog](reports/b71_s5/release-test_product_catalog.log) | 2026-09-16T02:45:00.718417+00:00 | 0.139 | 5 | `/usr/bin/python3 tests/mod_editor/test_product_catalog.py -v` |
| [release-test_phase1_packaging](reports/b71_s5/release-test_phase1_packaging.log) | 2026-09-16T02:45:00.718794+00:00 | 2.314 | 0 | `/usr/bin/python3 tests/mod_editor/test_phase1_packaging.py -v` |
| [release-test_nfl2k5_scorebug_template_release](reports/b71_s5/release-test_nfl2k5_scorebug_template_release.log) | 2026-09-16T02:45:00.858090+00:00 | 0.621 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py -v` |
| [final-test_nfl2k5_scorebug_v10_projection](reports/b71_s5/final-test_nfl2k5_scorebug_v10_projection.log) | 2026-09-16T02:45:01.300429+00:00 | 30.042 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py -v` |
| [final-test_nfl2k5_scorebug_versions](reports/b71_s5/final-test_nfl2k5_scorebug_versions.log) | 2026-09-16T02:45:02.780955+00:00 | 9.836 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_versions.py -v` |
| [final-test_scorebug_sprite_preview_qt](reports/b71_s5/final-test_scorebug_sprite_preview_qt.log) | 2026-09-16T02:45:12.617549+00:00 | 12.505 | 0 | `python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` |
| [final-test_scorebug_studio_panel_qt](reports/b71_s5/final-test_scorebug_studio_panel_qt.log) | 2026-09-16T02:45:25.122744+00:00 | 7.496 | 0 | `python3 tests/mod_editor/test_scorebug_studio_panel_qt.py -v` |
| [final-nfl2k5_scorebug_layout_test](reports/b71_s5/final-nfl2k5_scorebug_layout_test.log) | 2026-09-16T02:45:31.342725+00:00 | 1.465 | 0 | `python3 tests/nfl2k5_scorebug_layout_test.py -v` |
| [final-nfl2k5_scorebug_mod_project_test](reports/b71_s5/final-nfl2k5_scorebug_mod_project_test.log) | 2026-09-16T02:45:32.619299+00:00 | 1.361 | 0 | `python3 tests/nfl2k5_scorebug_mod_project_test.py -v` |
| [final-test_provider_integrity](reports/b71_s5/final-test_provider_integrity.log) | 2026-09-16T02:45:32.808461+00:00 | 0.208 | 5 | `python3 tests/mod_editor/test_provider_integrity.py -v` |
| [final-test_product_catalog](reports/b71_s5/final-test_product_catalog.log) | 2026-09-16T02:45:33.016619+00:00 | 0.133 | 5 | `python3 tests/mod_editor/test_product_catalog.py -v` |
| [final-test_phase1_packaging](reports/b71_s5/final-test_phase1_packaging.log) | 2026-09-16T02:45:33.150107+00:00 | 2.213 | 0 | `python3 tests/mod_editor/test_phase1_packaging.py -v` |
| [final-test_mod_build](reports/b71_s5/final-test_mod_build.log) | 2026-09-16T02:45:33.980367+00:00 | 1.867 | 0 | `python3 tests/mod_editor/test_mod_build.py -v` |
| [final-test_build_panel_qt](reports/b71_s5/final-test_build_panel_qt.log) | 2026-09-16T02:45:35.363245+00:00 | 2.874 | 0 | `python3 tests/mod_editor/test_build_panel_qt.py -v` |
| [final-test_nfl2k5_allocator_scaleout](reports/b71_s5/final-test_nfl2k5_allocator_scaleout.log) | 2026-09-16T02:45:35.847953+00:00 | 826.489 | 1 | `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py -v` |
| [final-test_nfl2k5_xbe_space](reports/b71_s5/final-test_nfl2k5_xbe_space.log) | 2026-09-16T02:45:38.237320+00:00 | 35.225 | 0 | `python3 tests/mod_editor/test_nfl2k5_xbe_space.py -v` |
| [gate-test_xbe_patch_memory_writes](reports/b71_s5/gate-test_xbe_patch_memory_writes.log) | 2026-09-16T02:46:43.012353+00:00 | 1558.063 | 0 | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py -v` |
| [gate-test_xbe_patch_cave_references](reports/b71_s5/gate-test_xbe_patch_cave_references.log) | 2026-09-16T02:46:43.012761+00:00 | 1752.922 | 0 | `python3 tests/mod_editor/test_xbe_patch_cave_references.py -v` |
| [corrected-test_nfl2k5_scorebug_freeze_v2](reports/b71_s5/corrected-test_nfl2k5_scorebug_freeze_v2.log) | 2026-09-16T02:48:22.247159+00:00 | 341.322 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` |
| [corrected-test_nfl2k5_scorebug_resources](reports/b71_s5/corrected-test_nfl2k5_scorebug_resources.log) | 2026-09-16T02:48:22.247583+00:00 | 374.772 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py -v` |
| [corrected-test_provider_integrity](reports/b71_s5/corrected-test_provider_integrity.log) | 2026-09-16T02:48:22.248237+00:00 | 11.27 | 0 | `/usr/bin/python3 tests/mod_editor/test_provider_integrity.py -v` |
| [registry-final](reports/b71_s5/registry-final.log) | 2026-09-16T02:48:23.369941+00:00 | 0.168 | 1 | `python3 -m mod_editor.capabilities.validate_registry` |
| [corrected-test_product_catalog](reports/b71_s5/corrected-test_product_catalog.log) | 2026-09-16T02:48:33.518505+00:00 | 0.158 | 0 | `/usr/bin/python3 tests/mod_editor/test_product_catalog.py -v` |
| [hydrate-evidence](reports/b71_s5/hydrate-evidence.log) | 2026-09-16T02:49:22.012005+00:00 | 0.06 | 0 | `python3 reports/b71_s5/hydrate_evidence.py` |
| [registry-hydrated](reports/b71_s5/registry-hydrated.log) | 2026-09-16T02:49:39.164026+00:00 | 0.191 | 1 | `python3 -m mod_editor.capabilities.validate_registry` |
| [registry-verified](reports/b71_s5/registry-verified.log) | 2026-09-16T02:50:18.895971+00:00 | 0.172 | 0 | `python3 -m mod_editor.capabilities.validate_registry` |
| [validators-plan](reports/b71_s5/validators-plan.log) | 2026-09-16T02:50:19.179614+00:00 | 0.289 | 0 | `python3 tools/validate_all_mod_editor_capabilities.py --list` |
| [shipping-test_nfl2k5_scorebug_sprite](reports/b71_s5/shipping-test_nfl2k5_scorebug_sprite.log) | 2026-09-16T02:51:48.985377+00:00 | 89.617 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` |
| [shipping-test_nfl2k5_scorebug_template_release](reports/b71_s5/shipping-test_nfl2k5_scorebug_template_release.log) | 2026-09-16T02:51:48.985865+00:00 | 0.561 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py -v` |
| [shipping-test_scorebug_sprite_preview_qt](reports/b71_s5/shipping-test_scorebug_sprite_preview_qt.log) | 2026-09-16T02:51:48.986468+00:00 | 12.701 | 0 | `/usr/bin/python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` |
| [repin-delivery](reports/b71_s5/repin-delivery.log) | 2026-09-16T02:53:37.807148+00:00 | 11.031 | 0 | `python3 packaging/repin.py --apply` |
| [gui-final](reports/b71_s5/gui-final.log) | 2026-09-16T02:57:08.561530+00:00 | 12.421 | 0 | `python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` |
| [allocator-final](reports/b71_s5/allocator-final.log) | 2026-09-16T02:58:13.129372+00:00 | 821.732 | 0 | `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py -v` |
| [registry-strict](reports/b71_s5/registry-strict.log) | 2026-09-16T02:59:22.338017+00:00 | 0.152 | 0 | `python3 -m mod_editor.capabilities.validate_registry` |
| [studio-page](reports/b71_s5/studio-page.log) | 2026-09-16T03:00:41.602450+00:00 | 12.6 | 0 | `python3 reports/b71_s5/prove_studio.py` |
| [studio-visible](reports/b71_s5/studio-visible.log) | 2026-09-16T03:04:45.727526+00:00 | 12.747 | 0 | `python3 reports/b71_s5/prove_studio.py` |
| [gui-visible](reports/b71_s5/gui-visible.log) | 2026-09-16T03:04:46.906154+00:00 | 12.416 | 0 | `python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` |
| [atlas-final](reports/b71_s5/atlas-final.log) | 2026-09-16T03:05:14.062975+00:00 | 7.252 | 1 | `python3 reports/b71_s5/prove_atlas.py` |
| [atlas-decoded](reports/b71_s5/atlas-decoded.log) | 2026-09-16T03:05:45.175987+00:00 | 7.502 | 0 | `python3 reports/b71_s5/prove_atlas.py` |
| [repin-visible](reports/b71_s5/repin-visible.log) | 2026-09-16T03:05:46.346445+00:00 | 11.759 | 0 | `python3 packaging/repin.py --apply` |
| [commit-preview](reports/b71_s5/commit-preview.log) | 2026-09-16T03:06:36.643743+00:00 | 0.047 | 0 | `git --git-dir=.scratch/b71-s5-git --work-tree=. commit -m 'Keep the native scorebug visible when Studio preview opens' -- mod_editor/gui/scorebug_sprite_preview_qt.py tests/mod_editor/test_scorebug_sprite_preview_qt.py` |
| [repin-previews](reports/b71_s5/repin-previews.log) | 2026-09-16T03:08:46.298265+00:00 | 11.472 | 0 | `python3 packaging/repin.py --apply` |
| [commit-previews](reports/b71_s5/commit-previews.log) | 2026-09-16T03:08:59.752050+00:00 | 0.268 | 0 | `git --git-dir=.scratch/b71-s5-git --work-tree=. commit -m 'Record native sprite previews for all requested states and both aspects' -- reports/b71_s5/atlas.png reports/b71_s5/ball_on_169.png reports/b71_s5/ball_on_169_compare_2x.png reports/b71_s5/ball_on_169_crop.png reports/b71_s5/ball_on_43.png reports/b71_s5/ball_on_43_compare_2x.png reports/b71_s5/ball_on_43_crop.png reports/b71_s5/build_testdisc71.py reports/b71_s5/clock_007_169.png reports/b71_s5/clock_007_169_compare_2x.png reports/b71_s5/clock_007_169_crop.png reports/b71_s5/clock_007_43.png reports/b71_s5/clock_007_43_compare_2x.png reports/b71_s5/clock_007_43_crop.png reports/b71_s5/day_169.json reports/b71_s5/day_169.png reports/b71_s5/day_43.json reports/b71_s5/day_43.png reports/b71_s5/down_1_169.png reports/b71_s5/down_1_169_compare_2x.png reports/b71_s5/down_1_169_crop.png reports/b71_s5/down_1_43.png reports/b71_s5/down_1_43_compare_2x.png reports/b71_s5/down_1_43_crop.png reports/b71_s5/down_2_169.png reports/b71_s5/down_2_169_compare_2x.png reports/b71_s5/down_2_169_crop.png reports/b71_s5/down_2_43.png reports/b71_s5/down_2_43_compare_2x.png reports/b71_s5/down_2_43_crop.png reports/b71_s5/down_3_169.png reports/b71_s5/down_3_169_compare_2x.png reports/b71_s5/down_3_169_crop.png reports/b71_s5/down_3_43.png reports/b71_s5/down_3_43_compare_2x.png reports/b71_s5/down_3_43_crop.png reports/b71_s5/down_4_169.png reports/b71_s5/down_4_169_compare_2x.png reports/b71_s5/down_4_169_crop.png reports/b71_s5/down_4_43.png reports/b71_s5/down_4_43_compare_2x.png reports/b71_s5/down_4_43_crop.png reports/b71_s5/flag_169.png reports/b71_s5/flag_169_compare_2x.png reports/b71_s5/flag_169_crop.png reports/b71_s5/flag_43.png reports/b71_s5/flag_43_compare_2x.png reports/b71_s5/flag_43_crop.png reports/b71_s5/fumble_169.png reports/b71_s5/fumble_169_compare_2x.png reports/b71_s5/fumble_169_crop.png reports/b71_s5/fumble_43.png reports/b71_s5/fumble_43_compare_2x.png reports/b71_s5/fumble_43_crop.png reports/b71_s5/goal_169.png reports/b71_s5/goal_169_compare_2x.png reports/b71_s5/goal_169_crop.png reports/b71_s5/goal_43.png reports/b71_s5/goal_43_compare_2x.png reports/b71_s5/goal_43_crop.png reports/b71_s5/hang_time_169.png reports/b71_s5/hang_time_169_compare_2x.png reports/b71_s5/hang_time_169_crop.png reports/b71_s5/hang_time_43.png reports/b71_s5/hang_time_43_compare_2x.png reports/b71_s5/hang_time_43_crop.png reports/b71_s5/hidden_play_clock_169.png reports/b71_s5/hidden_play_clock_169_compare_2x.png reports/b71_s5/hidden_play_clock_169_crop.png reports/b71_s5/hidden_play_clock_43.png reports/b71_s5/hidden_play_clock_43_compare_2x.png reports/b71_s5/hidden_play_clock_43_crop.png reports/b71_s5/hydrate_evidence.py reports/b71_s5/inches_169.png reports/b71_s5/inches_169_compare_2x.png reports/b71_s5/inches_169_crop.png reports/b71_s5/inches_43.png reports/b71_s5/inches_43_compare_2x.png reports/b71_s5/inches_43_crop.png reports/b71_s5/measurements.json reports/b71_s5/no_at_den_169.png reports/b71_s5/no_at_den_169_compare_2x.png reports/b71_s5/no_at_den_169_crop.png reports/b71_s5/no_at_den_43.png reports/b71_s5/no_at_den_43_compare_2x.png reports/b71_s5/no_at_den_43_crop.png reports/b71_s5/overtime_169.png reports/b71_s5/overtime_169_compare_2x.png reports/b71_s5/overtime_169_crop.png reports/b71_s5/overtime_43.png reports/b71_s5/overtime_43_compare_2x.png reports/b71_s5/overtime_43_crop.png reports/b71_s5/play_12_169.png reports/b71_s5/play_12_169_compare_2x.png reports/b71_s5/play_12_169_crop.png reports/b71_s5/play_12_43.png reports/b71_s5/play_12_43_compare_2x.png reports/b71_s5/play_12_43_crop.png reports/b71_s5/play_3_169.png reports/b71_s5/play_3_169_compare_2x.png reports/b71_s5/play_3_169_crop.png reports/b71_s5/play_3_43.png reports/b71_s5/play_3_43_compare_2x.png reports/b71_s5/play_3_43_crop.png reports/b71_s5/probe_scene.py reports/b71_s5/prove_atlas.py reports/b71_s5/prove_custom_design.py reports/b71_s5/prove_owner_bounds.py reports/b71_s5/prove_previews.py reports/b71_s5/prove_studio.py reports/b71_s5/refresh_manifest_projection.py reports/b71_s5/run_batch.py reports/b71_s5/run_final_suites.py reports/b71_s5/run_logged.py reports/b71_s5/run_xbe_gates.py reports/b71_s5/score_0_169.png reports/b71_s5/score_0_169_compare_2x.png reports/b71_s5/score_0_169_crop.png reports/b71_s5/score_0_43.png reports/b71_s5/score_0_43_compare_2x.png reports/b71_s5/score_0_43_crop.png reports/b71_s5/score_100_169.png reports/b71_s5/score_100_169_compare_2x.png reports/b71_s5/score_100_169_crop.png reports/b71_s5/score_100_43.png reports/b71_s5/score_100_43_compare_2x.png reports/b71_s5/score_100_43_crop.png reports/b71_s5/score_28_169.png reports/b71_s5/score_28_169_compare_2x.png reports/b71_s5/score_28_169_crop.png reports/b71_s5/score_28_43.png reports/b71_s5/score_28_43_compare_2x.png reports/b71_s5/score_28_43_crop.png reports/b71_s5/score_slabs_169.png reports/b71_s5/score_slabs_169_compare_2x.png reports/b71_s5/score_slabs_169_crop.png reports/b71_s5/score_slabs_43.png reports/b71_s5/score_slabs_43_compare_2x.png reports/b71_s5/score_slabs_43_crop.png reports/b71_s5/standard_169.png reports/b71_s5/standard_169_compare_2x.png reports/b71_s5/standard_169_crop.png reports/b71_s5/standard_43.png reports/b71_s5/standard_43_compare_2x.png reports/b71_s5/standard_43_crop.png reports/b71_s5/states.json reports/b71_s5/states_contact_sheet.png reports/b71_s5/studio-preview.json reports/b71_s5/studio-preview.png reports/b71_s5/timeouts_0_169.png reports/b71_s5/timeouts_0_169_compare_2x.png reports/b71_s5/timeouts_0_169_crop.png reports/b71_s5/timeouts_0_43.png reports/b71_s5/timeouts_0_43_compare_2x.png reports/b71_s5/timeouts_0_43_crop.png reports/b71_s5/timeouts_1_169.png reports/b71_s5/timeouts_1_169_compare_2x.png reports/b71_s5/timeouts_1_169_crop.png reports/b71_s5/timeouts_1_43.png reports/b71_s5/timeouts_1_43_compare_2x.png reports/b71_s5/timeouts_1_43_crop.png reports/b71_s5/timeouts_2_169.png reports/b71_s5/timeouts_2_169_compare_2x.png reports/b71_s5/timeouts_2_169_crop.png reports/b71_s5/timeouts_2_43.png reports/b71_s5/timeouts_2_43_compare_2x.png reports/b71_s5/timeouts_2_43_crop.png reports/b71_s5/timeouts_3_169.png reports/b71_s5/timeouts_3_169_compare_2x.png reports/b71_s5/timeouts_3_169_crop.png reports/b71_s5/timeouts_3_43.png reports/b71_s5/timeouts_3_43_compare_2x.png reports/b71_s5/timeouts_3_43_crop.png reports/b71_s5/verify_builder.py reports/b71_s5/volume.json` |
| [opacity-tests](reports/b71_s5/opacity-tests.log) | 2026-09-16T03:12:34.712258+00:00 | 97.035 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` |
| [repin-opacity](reports/b71_s5/repin-opacity.log) | 2026-09-16T03:12:35.882346+00:00 | 21.497 | 0 | `python3 packaging/repin.py --apply` |
| [gate-test_nfl2k5_cave_oracle](reports/b71_s5/gate-test_nfl2k5_cave_oracle.log) | 2026-09-16T03:12:41.075849+00:00 | 366.269 | 1 | `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py -v` |
| [manifest-opacity](reports/b71_s5/manifest-opacity.log) | 2026-09-16T03:12:52.093662+00:00 | 337.103 | 0 | `python3 reports/b71_s5/refresh_manifest_projection.py` |
| [preview-opacity](reports/b71_s5/preview-opacity.log) | 2026-09-16T03:12:53.273035+00:00 | 169.583 | 0 | `python3 reports/b71_s5/prove_previews.py` |
| [opacity-release-test_provider_integrity](reports/b71_s5/opacity-release-test_provider_integrity.log) | 2026-09-16T03:14:47.536045+00:00 | 10.988 | 0 | `/usr/bin/python3 tests/mod_editor/test_provider_integrity.py -v` |
| [opacity-release-test_product_catalog](reports/b71_s5/opacity-release-test_product_catalog.log) | 2026-09-16T03:14:47.536613+00:00 | 0.155 | 0 | `/usr/bin/python3 tests/mod_editor/test_product_catalog.py -v` |
| [opacity-release-test_phase1_packaging](reports/b71_s5/opacity-release-test_phase1_packaging.log) | 2026-09-16T03:14:47.537245+00:00 | 2.219 | 0 | `/usr/bin/python3 tests/mod_editor/test_phase1_packaging.py -v` |
| [opacity-release-test_scorebug_sprite_preview_qt](reports/b71_s5/opacity-release-test_scorebug_sprite_preview_qt.log) | 2026-09-16T03:14:47.692635+00:00 | 12.87 | 0 | `/usr/bin/python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` |
| [studio-opacity](reports/b71_s5/studio-opacity.log) | 2026-09-16T03:14:48.714501+00:00 | 13.016 | 0 | `python3 reports/b71_s5/prove_studio.py` |
| [repack-private](reports/b71_s5/repack-private.log) | 2026-09-16T03:15:11.590049+00:00 | 3.02 | 0 | `git --git-dir=.scratch/b71-s5-git --work-tree=. repack -d --local` |
| [gate-test_nfl2k5_owner_pairwise_composition](reports/b71_s5/gate-test_nfl2k5_owner_pairwise_composition.log) | 2026-09-16T03:15:55.935283+00:00 | 2966.963 | 0 | `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -v` |
| [owner-bounds-final](reports/b71_s5/owner-bounds-final.log) | 2026-09-16T03:18:13.515821+00:00 | 20.322 | 0 | `python3 reports/b71_s5/prove_owner_bounds.py` |
| [custom-design-final](reports/b71_s5/custom-design-final.log) | 2026-09-16T03:18:14.684115+00:00 | 11.362 | 0 | `python3 reports/b71_s5/prove_custom_design.py` |
| [projection-identity](reports/b71_s5/projection-identity.log) | 2026-09-16T03:19:04.061687+00:00 | 0.227 | 0 | `python3 reports/b71_s5/prove_projection_identity.py` |
| [oracle-current](reports/b71_s5/oracle-current.log) | 2026-09-16T03:19:04.387153+00:00 | 360.839 | 0 | `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py -v` |
| [registry-current](reports/b71_s5/registry-current.log) | 2026-09-16T03:19:05.561773+00:00 | 0.157 | 0 | `python3 -m mod_editor.capabilities.validate_registry` |
| [repin-opaque-commit](reports/b71_s5/repin-opaque-commit.log) | 2026-09-16T03:19:26.866598+00:00 | 11.526 | 0 | `python3 packaging/repin.py --apply` |
| [commit-opaque](reports/b71_s5/commit-opaque.log) | 2026-09-16T03:19:40.413750+00:00 | 0.424 | 0 | `git --git-dir=.scratch/b71-s5-git --work-tree=. commit -m 'Sample atlas strips opaquely and prove the final native sprite output' -- data/nfl2k5_cave_reservations.json docs/mod_editor/2k5_mod_studio_changelog.md mod_editor/core/nfl2k5_scorebug_sprite.py mod_editor/core/providers.py reports/b71_s5/ball_on_169.png reports/b71_s5/ball_on_169_compare_2x.png reports/b71_s5/ball_on_169_crop.png reports/b71_s5/ball_on_43.png reports/b71_s5/ball_on_43_compare_2x.png reports/b71_s5/ball_on_43_crop.png reports/b71_s5/clock_007_169.png reports/b71_s5/clock_007_169_compare_2x.png reports/b71_s5/clock_007_169_crop.png reports/b71_s5/clock_007_43.png reports/b71_s5/clock_007_43_compare_2x.png reports/b71_s5/clock_007_43_crop.png reports/b71_s5/day_169.json reports/b71_s5/day_169.png reports/b71_s5/day_43.json reports/b71_s5/day_43.png reports/b71_s5/down_1_169.png reports/b71_s5/down_1_169_compare_2x.png reports/b71_s5/down_1_169_crop.png reports/b71_s5/down_1_43.png reports/b71_s5/down_1_43_compare_2x.png reports/b71_s5/down_1_43_crop.png reports/b71_s5/down_2_169.png reports/b71_s5/down_2_169_compare_2x.png reports/b71_s5/down_2_169_crop.png reports/b71_s5/down_2_43.png reports/b71_s5/down_2_43_compare_2x.png reports/b71_s5/down_2_43_crop.png reports/b71_s5/down_3_169.png reports/b71_s5/down_3_169_compare_2x.png reports/b71_s5/down_3_169_crop.png reports/b71_s5/down_3_43.png reports/b71_s5/down_3_43_compare_2x.png reports/b71_s5/down_3_43_crop.png reports/b71_s5/down_4_169.png reports/b71_s5/down_4_169_compare_2x.png reports/b71_s5/down_4_169_crop.png reports/b71_s5/down_4_43.png reports/b71_s5/down_4_43_compare_2x.png reports/b71_s5/down_4_43_crop.png reports/b71_s5/flag_169.png reports/b71_s5/flag_169_compare_2x.png reports/b71_s5/flag_169_crop.png reports/b71_s5/flag_43.png reports/b71_s5/flag_43_compare_2x.png reports/b71_s5/flag_43_crop.png reports/b71_s5/fumble_169.png reports/b71_s5/fumble_169_compare_2x.png reports/b71_s5/fumble_169_crop.png reports/b71_s5/fumble_43.png reports/b71_s5/fumble_43_compare_2x.png reports/b71_s5/fumble_43_crop.png reports/b71_s5/goal_169.png reports/b71_s5/goal_169_compare_2x.png reports/b71_s5/goal_169_crop.png reports/b71_s5/goal_43.png reports/b71_s5/goal_43_compare_2x.png reports/b71_s5/goal_43_crop.png reports/b71_s5/hang_time_169.png reports/b71_s5/hang_time_169_compare_2x.png reports/b71_s5/hang_time_169_crop.png reports/b71_s5/hang_time_43.png reports/b71_s5/hang_time_43_compare_2x.png reports/b71_s5/hang_time_43_crop.png reports/b71_s5/hidden_play_clock_169.png reports/b71_s5/hidden_play_clock_169_compare_2x.png reports/b71_s5/hidden_play_clock_169_crop.png reports/b71_s5/hidden_play_clock_43.png reports/b71_s5/hidden_play_clock_43_compare_2x.png reports/b71_s5/hidden_play_clock_43_crop.png reports/b71_s5/inches_169.png reports/b71_s5/inches_169_compare_2x.png reports/b71_s5/inches_169_crop.png reports/b71_s5/inches_43.png reports/b71_s5/inches_43_compare_2x.png reports/b71_s5/inches_43_crop.png reports/b71_s5/measurements.json reports/b71_s5/no_at_den_169.png reports/b71_s5/no_at_den_169_compare_2x.png reports/b71_s5/no_at_den_169_crop.png reports/b71_s5/no_at_den_43.png reports/b71_s5/no_at_den_43_compare_2x.png reports/b71_s5/no_at_den_43_crop.png reports/b71_s5/overtime_169.png reports/b71_s5/overtime_169_compare_2x.png reports/b71_s5/overtime_169_crop.png reports/b71_s5/overtime_43.png reports/b71_s5/overtime_43_compare_2x.png reports/b71_s5/overtime_43_crop.png reports/b71_s5/play_12_169.png reports/b71_s5/play_12_169_compare_2x.png reports/b71_s5/play_12_169_crop.png reports/b71_s5/play_12_43.png reports/b71_s5/play_12_43_compare_2x.png reports/b71_s5/play_12_43_crop.png reports/b71_s5/play_3_169.png reports/b71_s5/play_3_169_compare_2x.png reports/b71_s5/play_3_169_crop.png reports/b71_s5/play_3_43.png reports/b71_s5/play_3_43_compare_2x.png reports/b71_s5/play_3_43_crop.png reports/b71_s5/projection-identity.json reports/b71_s5/prove_projection_identity.py reports/b71_s5/score_0_169.png reports/b71_s5/score_0_169_compare_2x.png reports/b71_s5/score_0_169_crop.png reports/b71_s5/score_0_43.png reports/b71_s5/score_0_43_compare_2x.png reports/b71_s5/score_0_43_crop.png reports/b71_s5/score_100_169.png reports/b71_s5/score_100_169_compare_2x.png reports/b71_s5/score_100_169_crop.png reports/b71_s5/score_100_43.png reports/b71_s5/score_100_43_compare_2x.png reports/b71_s5/score_100_43_crop.png reports/b71_s5/score_28_169.png reports/b71_s5/score_28_169_compare_2x.png reports/b71_s5/score_28_169_crop.png reports/b71_s5/score_28_43.png reports/b71_s5/score_28_43_compare_2x.png reports/b71_s5/score_28_43_crop.png reports/b71_s5/score_slabs_169.png reports/b71_s5/score_slabs_169_compare_2x.png reports/b71_s5/score_slabs_169_crop.png reports/b71_s5/score_slabs_43.png reports/b71_s5/score_slabs_43_compare_2x.png reports/b71_s5/score_slabs_43_crop.png reports/b71_s5/standard_169.png reports/b71_s5/standard_169_compare_2x.png reports/b71_s5/standard_169_crop.png reports/b71_s5/standard_43.png reports/b71_s5/standard_43_compare_2x.png reports/b71_s5/standard_43_crop.png reports/b71_s5/states_contact_sheet.png reports/b71_s5/studio-preview.png reports/b71_s5/timeouts_0_169.png reports/b71_s5/timeouts_0_169_compare_2x.png reports/b71_s5/timeouts_0_169_crop.png reports/b71_s5/timeouts_0_43.png reports/b71_s5/timeouts_0_43_compare_2x.png reports/b71_s5/timeouts_0_43_crop.png reports/b71_s5/timeouts_1_169.png reports/b71_s5/timeouts_1_169_compare_2x.png reports/b71_s5/timeouts_1_169_crop.png reports/b71_s5/timeouts_1_43.png reports/b71_s5/timeouts_1_43_compare_2x.png reports/b71_s5/timeouts_1_43_crop.png reports/b71_s5/timeouts_2_169.png reports/b71_s5/timeouts_2_169_compare_2x.png reports/b71_s5/timeouts_2_169_crop.png reports/b71_s5/timeouts_2_43.png reports/b71_s5/timeouts_2_43_compare_2x.png reports/b71_s5/timeouts_2_43_crop.png reports/b71_s5/timeouts_3_169.png reports/b71_s5/timeouts_3_169_compare_2x.png reports/b71_s5/timeouts_3_169_crop.png reports/b71_s5/timeouts_3_43.png reports/b71_s5/timeouts_3_43_compare_2x.png reports/b71_s5/timeouts_3_43_crop.png reports/b71_s5/volume.json tests/mod_editor/test_nfl2k5_allocator_scaleout.py tests/mod_editor/test_nfl2k5_scorebug_sprite.py` |
| [repack-corrected](reports/b71_s5/repack-corrected.log) | 2026-09-16T03:20:49.387292+00:00 | 3.12 | 0 | `git --git-dir=.scratch/b71-s5-git --work-tree=. repack -d --local` |

Failures are retained as evidence: early compiler/fixture bring-up; historical tests assuming the old cave address, FONT-only profiles or small XBE; a projection that detected edits during observation and refused to publish; canonical registry formatting and inherited missing evidence. The final rows record the corrected checks. No native or release gate was weakened to accept foreign bytes, skip registry files, or claim gameplay.
