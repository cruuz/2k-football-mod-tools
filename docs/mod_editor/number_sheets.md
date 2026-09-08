# Import number sheets 0-9

Choose a physical uniform set in 2K5 Studio, then **Import number sheet 0-9**.
Choose Jersey, Helmet, or Arm / shoulder, and select your sheet's layout.
The layout chooser requires the Discord batch 2 GUI wiring.

Use ten equal rectangular cells. Supported layouts read as follows:

| Layout | Digit order | Example with 128 x 128 cells |
| --- | --- | --- |
| One row | 0 1 2 3 4 5 6 7 8 9, left to right | 1280 x 128 |
| One column | 0 at the top through 9 at the bottom | 128 x 1280 |
| Five columns, two rows | First row 0 1 2 3 4; second 5 6 7 8 9 | 640 x 256 |
| Two columns, five rows | 0 1; 2 3; 4 5; 6 7; 8 9 | 256 x 640 |

PNG with transparency is recommended. Other Pillow-readable images are decoded
to RGBA; JPEG cannot preserve transparency. Export a flat raster image, not a
Photoshop document or font file. Only the first frame is used; EXIF orientation
is applied before layout. There must be no grid lines, labels, outside border,
or gaps between cells. Put the intended padding inside each cell. Center and
align each digit against the exported game digit for that exact set and family;
the importer does not detect glyph bounds, remove a background or find digits.
It cannot recognize a sheet in 1-9-0 order or diagnose drawn-in guides.

Cell width and height may differ. Each whole cell, including its transparent
padding, is resized independently to the live catalog's target dimensions.
The size notes report the detected layout, cell size, slot size, enlargement
and any change in shape. This can stretch artwork if its aspect differs. Jersey, helmet and arm slots
can have different sizes; export their original PNGs to check the shape first.
Do not crop every character tightly: a narrow 1 should retain the same cell
and baseline convention as the other digits. Compare alpha and margins at
native size before making the disc. In-game placement still needs a witness.

For equal cells the sheet width must divide evenly by its column count, and
height by its row count. The error gives actual dimensions and exact divisors.
The input must be a regular file of at most 128 MiB and at most 16 million
pixels. Oversized images are rejected before full pixel conversion.

Older API callers can retain automatic orientation for a strip at least five
times longer than its other side. Less elongated inputs require an explicit
layout rather than guessing. Automatic orientation does not recognize grids.

Studio stages all ten digits through one validated Team Kit import and one
Undo action. Save the project and include it in the disc build. It does not
create a sheet for you. To author one, use an image editor and the exported
original digits as size and padding references. The earlier Windows long-path
fix is separate from this layout fix.

## Clean digit recipe

The r64 number quality correction is **EXPERIMENTAL / UNWITNESSED**. Its encoded
preview requires the protected GUI patch listed in WIRING.md.

1. Export the original digits for the exact physical team, style, side and
   family. Match those cell dimensions and their padding. Jersey digits are
   64x64; helmet and arm digits can be 32x32 or 64x64 depending on the target.
   Do not assume every family or team uses the same dimensions.
2. Create ten equal cells in 0-9 order with no gutters or outside border.
   For 64x64 cells use 640x64, 64x640, 320x128 (5x2), or 128x320 (2x5).
   Keep a narrow 1 on the same canvas and baseline as a wide 8. Check that
   artwork never crosses a cell boundary. The importer cannot identify a
   wrongly centered glyph, a digit order mistake or hidden guides.
3. Use flat fills and distinct outline colours. Two or three solid colours
   plus transparent padding are a useful starting point. Avoid photographic
   noise, glow and repeated resize/export cycles. Keep outlines several pixels
   wide at the actual game-slot size when the design permits; a one-pixel line
   has very little coverage in a small camera view. This is guidance, not a
   universal minimum or a guarantee for every font and camera.
4. Export PNG with straight (ordinary, unassociated) alpha. RGBA PNG is easiest
   to inspect; indexed PNG with transparency also works. Keep soft edges in
   alpha, with the edge's real RGB colour behind them. Do not paint a checkerboard
   or a background into the file. Do not manually multiply RGB by alpha: this
   darkens the edge twice when treated as ordinary PNG. The importer cannot
   reliably distinguish that mistake from intentionally dark art and does not
   guess a repair. Re-export from the authoring project if needed.
5. Select the matching uniform set, number family and layout, then choose the
   PNG. Read the cell-to-slot notes. A 62x62 or 66x66 cell is resized, including
   its padding; matching the native size avoids that extra conversion. A width
   that does not divide into equal cells is refused with its dimensions.
6. In the encoded preview, inspect all ten rows, all smaller levels, and both
   light and dark backgrounds. The level columns magnify each saved texture to
   a 32-pixel cell. The 24- and 12-pixel views estimate how reduced textures
   combine; they do not simulate jersey shading, UV distortion or the actual
   camera. If the fill or outline changes too much, cancel and simplify the art.
7. Choose **Import all ten digits**. Save the project and build with those edits.
   All ten still import as one Team Kit transaction and one Undo action. If any
   texture cannot fit at the allowed quality, preview refuses before staging.
   Verify the numbers from the broadcast camera and up close in the game.

The game stores palettized P8 digits. That means 8-bit indices into one shared
256-entry palette with **8 bits of alpha per entry**, not one-bit transparency.
The encoder regenerates every declared smaller level from the imported base
using area coverage and fits the whole chain to that one palette. It preserves
up to sixteen exact solid colours; artwork with more solid shades is approximated
and reported. Compression fitting may choose a smaller palette, down to a
16-entry budget. A simple two-colour design can naturally use fewer entries
without losing colours. Complicated art that cannot fit at this floor is refused.
Palette size is not a promise that every font fits: each digit's compressed byte
budget is fixed by its original slot, and different teams have different budgets.

Making a digit smaller inside the same cell does not increase texture resolution,
add colours or repair a bad mip filter. Making the whole sheet smaller introduces
another resize if the cells then differ from the slots. Author at the native
size or resize from a clean larger master once, then judge the encoded small
views. The new preview and error messages are more useful than the PNG file size.
