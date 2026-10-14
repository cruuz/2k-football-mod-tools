# nm1 indicator atlas contract v1

This is the implementation contract for the Opus alphabet. No new letters are
drawn by nm1. The retail-derived test atlas is private, marked PLACEHOLDER, and
must not enter a release or the repository.

## Authoring files

Directory: `data/nfl2k5_indicator_names/`. A custom folder can be selected with
the Studio build plan's `indicator_names_folder` field.

When the authored files arrive, add `data/nfl2k5_indicator_names/atlas.png` and
`data/nfl2k5_indicator_names/metrics.json` to `packaging/release-allowlist.txt`.
They are deliberately not required release inputs until the final art exists.
Do not stage the private retail-derived placeholder. Set `placeholder` to false
and record the authored artwork's provenance in the final metrics file.

- `atlas.png`: **256 by 128**, RGBA PNG. White RGB (255,255,255) with alpha
  coverage; transparent background. No font files. Leave one transparent pixel
  around each glyph inside its rectangle. The compiler bakes a one-pixel dark
  outline mechanically; do not paint an outline in the source PNG.
- `metrics.json`: UTF-8 JSON, schema `nfl2k5_indicator_names/v1`.

Required keys:

```json
{
  "schema": "nfl2k5_indicator_names/v1",
  "atlas": [256, 128],
  "texture": "atlas.png",
  "placeholder": false,
  "provenance": "Opus authored scorebug-style alphabet",
  "cap_height": 11,
  "line_advance": 17,
  "baseline": 15,
  "outline": 1,
  "glyphs": {
    "A": {"rect": [0, 0, 13, 13], "quad": [-1, 3, 12, 16], "advance": 12},
    " ": {"rect": [0, 0, 0, 0], "quad": [0, 0, 0, 0], "advance": 4}
  }
}
```

The example is illustrative, not a complete alphabet. Supply exactly **A-Z,
0-9, apostrophe `'`, hyphen `-`, period `.`, and space**: 40 entries. Each rect
is a half-open pixel rectangle, with no overlap. Each quad gives left, top,
right and bottom in native HUD pixels, relative to the text origin. Its width
and height must equal the rectangle's width and height. Advances are positive
integer HUD pixels, independent of the outlined quad width. Space has zero
rect/quad and a positive advance. The baseline is metadata for authoring; quad
coordinates contain the actual bearing. Lowercase game strings map to the
corresponding uppercase glyph records without changing roster strings. Thus
`St. Brown`, `O'Connell`, `Smith-Njigba` render as uppercase names retaining
their punctuation and spaces. Other ASCII characters are blank advances.

An optional easy packing grid is eight columns of 32 by 24 cells, five rows,
ordered A-Z, 0-9, apostrophe, hyphen, period, space. Rectangles can be tighter
than their cells. Grid cell i starts at `(32*(i%8), 24*(i//8))`. The final eight
rows of the 128-pixel sheet are unused. Keep every ink pixel at least one pixel
inside its declared rect for the outline. Do not change existing scorebug art.

The **11-pixel cap height** comes from the retail indicator's actual FONT4 A
quad: y=4..15, line advance 17. Preserve that height for the first live comparison.
The earlier 14-pixel offline GOAL demonstration was provisional and is superseded.

## Disc and runtime representation

The compiler creates a native private **FONT** resource named
`icon_controller_star`, using the existing UTF-16 name at XBE VA `0xE6C16C`.
Resource lookup includes the FOURCC, so the controller texture is unaffected.
The FONT has one ASCII range 32..126, per-character advances and quads, lowercase
aliases, and a **256 by 128 swizzled P8 texture** with a 1,024-byte BGRA palette.
Palette indices 1..15 are white with 16 alpha levels; 16..30 are dark RGB
(16,16,16) with the same coverage levels. Zero is transparent. The generated
one-pixel outline is eight-neighbor alpha dilation around each glyph separately.

Location: `vc_53450030/0`, outer 346 (`gamedata.iff`), inside the existing
appended sprite scorebug scene's fixed span. The base disc's scene starts at
outer-relative **3280608**, span **24480**. Its decoded scene stays byte-identical
but is stored using native VC-LZ, followed by the compressed private FONT. The
two chunks exactly fill the old span. The following windmeter FONT and every
outer/disc offset remain fixed. The installer locates and validates this scene;
it does not assume the enclosing pack's disc offset. This requires the sprite
scorebug allocation. A font that cannot fit is rejected before writing.

The indicator initializer at `0xF9FE5..0xFA012` binds this FONT directly through
the native registry, preserving its material initialization. All global FONT
slots remain intact. No visibility changes are included in this font binding;
the live matrix determines whether a separate visibility fix is needed.

The mechanically generated placeholder is saved only under the job's private
scratch folder and has `placeholder: true` and retail donor provenance. It is
compiled by the exact same path as the final authored atlas. The repair receipt
records its status and atlas hashes. Final art replaces the two authoring files,
not executable source or per-name textures.
