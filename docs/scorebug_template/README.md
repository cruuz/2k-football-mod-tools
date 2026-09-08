# Repaintable ESPN scorebar template, v10

**EXPERIMENTAL / UNWITNESSED.** This is the default art for the existing static
`scorebug` option. It uses new pixels and Noah's supplied vector design lineage.
The frame, logo and team-block art do not come from the game disc. The installer
still needs the user's game for the native resource structure and live fonts.

Copy this entire folder before painting. Edit the PNGs in **`1x/`**. Those are
the actual inputs, at the game's atlas resolution. For a larger pixel canvas,
edit `2x/` and set `"source_scale": 2` in `layout.json`. The compiler takes
every second pixel using nearest-neighbour reduction. It does not merge the
two sets, upscale the game's allocation or silently choose between them.

Each PNG has an editable SVG sibling. The SVGs contain simple vector pixel
runs, with no font or external renderer dependency. If you edit an SVG, export
it back to its matching PNG at exactly the original canvas size, without
antialiasing or additional colours. `master_1x.svg` and `master_2x.svg` arrange
the layers in the 640x480 HUD space. They contain no baked live text. The
original community vectors are preserved in `lineage/`; those originals are
design sources, not the runtime layout or active compiler inputs.

| Repaint this 1x PNG | Native canvas | Role in the 640x480 HUD |
| --- | --- | --- |
| `frame.png` | 64x8 | Outer rim and dark frame, [84,381,560,429] |
| `left_mark.png` | 64x16 | Geometric ESPN/NFL mark, [88,393,156,417] |
| `away_block.png` | 32x16 | Away block shading, [160,383,274,427] |
| `home_block.png` | 32x16 | Home block shading, [438,383,558,427] |
| `away_score.png` | 12x16 | Dark score backing within the away block |
| `home_score.png` | 12x16 | Dark score backing within the home block |
| `clock_quarter.png` | 64x12 | Recessed light clock cell, [278,405,434,427] |
| `down.png` | 64x12 | Red down cell, [278,383,434,404] |

Coordinates are half-open `[left, top, right, bottom]`. The small source images
stretch to these cells, so narrow borders can become thick at HUD scale. The
master is a painting guide; the native harness is the evidence for actual
transformed positions and filtering. Native SHAP UV scale/bias and bilinear
sampling can blend pixels near cell boundaries.

Score layers replace their part of the team layers, including alpha. Paint
both if you want a continuous gradient. The away score covers columns 20..31
of its block; the home score covers columns 0..11. No score, abbreviation,
clock, quarter or down string should be painted into a background layer.

## Compile and install

From the repository or installed Studio root:

```sh
python3 -m mod_editor.core.nfl2k5_scorebug_template validate \
  --folder /path/to/my-scorebar --receipt /path/to/template-check.json

python3 -m mod_editor.core.nfl2k5_scorebug_template apply \
  --folder /path/to/my-scorebar --image /path/to/output-copy.iso \
  --receipt /path/to/scorebar-install.json
```

`validate` checks the source files without a game. `apply` compiles and checks
the actual fixed game allocation before writing anything. It updates an
**existing output copy** in place, just like the build's static scorebug step;
it does not copy a source disc or produce a second full disc by itself.
The same backend is `tools.nfl2k5_scorebug_layout.apply_in_place(path,
scorebug_folder=folder)`. A blank folder uses this shipped default.

The existing Studio **Experimental ESPN scorebar** checkbox already installs
v10 through that backend. The **Scorebar folder** field follows the existing
Hi-res folder pattern; its exact protected BuildPlan/GUI/release changes are
the v10 section at the top of `WIRING.md`. That field is a handoff for the
integration owner and is **not present in this worktree's GUI yet**. Until it
is wired, use the command above for a custom template. The new runtime module
and every file in this folder must be added to the release allowlist as listed
there before packaging. No template change enables the diagnostic runtime.

`atlas_1x.png` and `atlas_2x.png` are generated default packing previews, not
compiler inputs. A custom install receipt records the selected PNG hashes,
layout hash, exact RGBA hash, installed resource hashes and XBE edits. Reapply
with the same folder returns the same bytes. Changing a previously installed
folder or mixing resources from different versions refuses; rebuild from a
supported clean base. Keep the receipt and the exact source folder together.

## Palette and fixed allocation

The P8 atlas is **64x64, at most 256 distinct RGBA colours across all selected
layers**, including alpha. The default has 16. Each source file is capped at
512 KiB, and the required canvas size is checked before decoding pixels.
Export all layers with a shared palette. A PNG with too many colours or the
wrong dimensions is refused with its filename and an instruction to fix it.

The compiler uses an exact sorted palette; it never reduces your colours to
force an install. Even a valid 256-colour image can be too detailed to fit.
If that happens, simplify gradients or use fewer colours. The compressed
`score_buga` span stays **2432 bytes**. The scene stays **4832 bytes**.
`nfl_vc_lz_fill` refits them with the complete 32-byte wrapper unchanged,
especially **wrapper +0x14 = 16**, the loader's overlapping-decode allowance.
Increasing that word is not a supported workaround. Native decompression and
host decode must yield the same bytes.

## Fixed cells and live text

This compiler changes artwork in eight layers. It cannot add a cell, alter
topology, move anchors or replace a FONT object. Changes to the pinned layout,
HUD rails or live anchors in `layout.json` are refused. Those fields document
the contract; only `source_scale` is an authoring control. The frame remains
one 476x48 bar, and all active geometry/text must pass the v9 containment
predicate. Widescreen v3 contracts X by 27/32 about 320, with unchanged Y.

The live text's scene anchors and ARGB colours are recorded in `layout.json`.
Scores and down text are white; team abbreviations are white with native
possession yellow; quarter, clock and play clock use dark `FF111118` on the
light cell. Repainting that cell dark will make its text hard to read. Changing
those colours requires changes to the existing XBE data fields and new checks;
editing the descriptive JSON colour entries does not change the executable.

**Font decision:** the new condensed digit/letter sheet is in
`glyphs/1x/broadcast_glyphs.png`, with its 2x/SVG siblings and character metrics
in `glyphs/glyphs.json`. It is authored from geometric pixel rows, not a disc
font or an installed typeface. It is a **staged source**, not installed live.
The actual scorebug uses FONT objects from the shared global font collection;
replacing `digital_font` or painting this P8 frame cannot change those glyphs.
Installing an isolated new FONT needs a new resource plus a font binding under
the runtime owner. Replacing a shared FONT would also change unrelated menus.
That isolated install is outside the static two-resource path, so v10 uses
the brief's live-text fallback: **font1** for clock/down/quarter/events,
**font5** for abbreviations and **font2** for larger 25-pixel score glyphs.
Only the two existing score font-slot words change from 0 to 1. Global FONT
resources, glyph metrics, cached score strings and rotation code stay intact.
The result is a broadcast-inspired adaptation, not exact font/logo equality.

## Team variants and timeouts for the runtime owner

`teams.json` preserves the supplied 32-club palette table. `teams/1x/ABBR.png`
and the matching 2x/SVG files provide independently repaintable block art for
all 32 teams. The default static install never selects a team from this set.
`stage_team_variant("LV", side="away", folder=folder)` in the template module
packs a complete 64x64 side variant, preserves the independent score backing
and leaves other cells alone. `encode_span(retail_atlas_span, variant)` refits
it with the same wrapper rule. All 32 teams on both sides are compile-tested.
These helpers return staged data and receipts; they do not install a selector.
The future owner must resolve the current identity, clone/bind independent
away/home atlases and coordinate native material visibility. Away parent 23
(`away_score1`) currently shares `zscore_buga` with home parent 26
(`home_score1`). The existing staging contract names `hscore_buga` for a
separate home material and requires coordination of element 2's visibility.
V10's 64x64 packing is not the older runtime's 128x32 panel format; migrate
the binding scene and collection together rather than enabling that old scene.

`optional/1x/timeout_marks.png` has three newly drawn marks. It is **not packed
or installed**, and its desired HUD rectangles are documented in `layout.json`.
The runtime owner must read real 0..3 remaining timeouts, select the appropriate
art/state, and update it at each timeout and reset. Setting `live_timeouts` true
in this static template refuses. Neither a palette table nor a row of painted
dashes implements a live counter. The earlier runtime entry freeze remains a
separate diagnostic task.

## Reproduce the default and its proof

`python3 tools/nfl2k5_scorebug_template_art.py` regenerates the **default** PNGs,
SVGs, metadata and atlas previews. It overwrites those authored files, so do not
run it on a custom painting folder you want to keep. It needs only Python and
Pillow; no system font, network, game art or SVG renderer is used.

For a reviewed new default, maintainers can add `--write-release-catalog`
and update the printed catalog hash in the release checker. This pins the
exact shipped PNGs. Custom paintings belong in a separate input folder and
do not need a release-catalog change.

```sh
python3 -m tools.nfl2k5_scorebug_projection \
  --pack /path/to/extracted/vc_53450030/0 \
  --xbe /path/to/extracted/default.xbe \
  --folder /path/to/my-scorebar --output /path/to/proof
```

The proof uses native resource relocation, setup, score rotation, live
formatters and glyph submissions in a bounded CPU fixture, then a labelled
software raster. It runs no game or display. The comparison uses the original
research-hub broadcast JPEG; the old `target_*.png` files are staged mockups,
despite their filenames. See `ASTRA_SCOREBUG_V10_REPORT.md` for exact tests,
evidence limits and Noah's played-game witness list.

## Default bar and team outlines

Leaving the artwork folder blank selects the experimental v3 bar, whose
team outlines and panels use live retail team colours. Its separate white
outline mask is generated by `nfl2k5_scorebug_exact.py`; it does not come from
these PNG layers. The centre and decorative timeout marks remain neutral.

Selecting this folder explicitly keeps the lossless v10 artwork contract.
Its eight PNG layers, saved colours, layout and compiled game bytes are
unchanged by the team-outline revision. Scorebar Studio opens and saves this
folder byte for byte. Editing these PNGs does not enable live outline tint.
