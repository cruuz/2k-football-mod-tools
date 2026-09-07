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
This can stretch artwork if its aspect differs. Jersey, helmet and arm slots
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
