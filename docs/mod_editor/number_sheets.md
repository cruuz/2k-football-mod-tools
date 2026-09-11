# Import number sheets 0-9

Choose the physical uniform set in Uniforms & Equipment, then Import number
sheet 0-9. Choose Jersey, Helmet, or Arm / shoulder, the layout, and Match
retail size. The original game uses different sizes and different compressed
budgets for individual digits, even within the same uniform.

Use a transparent PNG with ten equal cells in 0-9 order. Leave out labels,
guides, gutters and outside borders. These four layouts work:

| Layout | Order | Size with 64x64 cells |
| --- | --- | --- |
| One row | 0 through 9 from left to right | 640x64 |
| One column | 0 at the top, 9 at the bottom | 64x640 |
| Five columns, two rows | 0-4 above 5-9 | 320x128 |
| Two columns, five rows | 0 1, then 2 3, through 8 9 | 128x320 |

Use one flat fill colour and one outline colour. Keep the glyph inside its
cell with a transparent margin. Avoid gradients, noise and glow. AI output
usually needs cleanup. The tool now applies that cleanup before encoding.
It does not find a wrong digit order, remove a painted background or redraw
an illegible number. JPEG cannot retain transparency.

Use ordinary straight-alpha PNG. Do not darken RGB by multiplying it by
alpha yourself. That error is indistinguishable from intentionally dark
art, so re-export it from your image editor with ordinary transparency.

Match retail size measures the original digit for the selected slot. It
scales your glyph to fit inside that box, preserves its aspect, centres it,
and retains at least the original transparent margins. A very wide glyph
can become shorter when fitted. Compare the entire family before importing.
As authored is the expert choice for preserving your cell placement. It
still applies colour and edge cleanup, but never shrinks the registration
to rescue a compressed slot. The choice travels with the staged PNG and
saved project. Re-saving that PNG in another editor may remove the choice;
preview again after editing.

The tool binds faint alpha to transparent and nearly solid alpha to opaque,
merges nearby shades, limits the soft edge to one texel, and filters with
premultiplied colour before saving ordinary straight alpha. It extends edge
colours into invisible pixels so filtering cannot pull in transparent black.
Every smaller texture level is rebuilt with a clear border, matching the
retail mip margins, and all levels share one palette.
The receipt records the box, scale, cleanup and selected palette.

The encoder first tries the usual palette budgets down to 16 colours. Clean
one-fill, one-outline art can also try 12 and 8 colours while keeping both
regions. Match retail size may then try an additional 6% or 12% reduction.
It does not erase an outline or accept a one-colour version of a two-colour
number to force a fit. A digit that still cannot fit stays retail.

In the preview, each top sample is what the build will write and each bottom
sample is the original retail digit at the same level. KEPT RETAIL marks a
fallback beside the digit. The Import button counts the outcome, for example
Import 7 digits, 3 kept retail. The 57 pair and small size views estimate how
the digits look together. They do not reproduce camera perspective or jersey
lighting. Inspect every row and the notes before accepting.

The ten cells stage together through Team Kit as one Undo action. Check my
images and the build use the same encoding policy and say which digits will
stay retail. Load the game source so Check my images can measure the original
registration. Save the project and include its edits in the build. Verify
front, back, shoulder and helmet numbers in play, both up close and from the
broadcast camera. In-game appearance remains UNWITNESSED until played.

Other equal cell sizes also work. Width must divide by the number of columns
and height by the number of rows. The source must be a regular file no larger
than 128 MiB or 16 million pixels. Automatic orientation identifies long rows
or columns; select either grid layout explicitly.

## Why did some digits stay old, look larger, or bleed?

Each digit has its own small compressed slot. A noisy number can fit one
slot and overflow another, which kept the original digit and made the set
look mixed. Filling the whole cell also makes a number wider than the
original. An opaque edge can smear when the game samples past the cell,
and transparent black can darken a soft edge. The new cleanup and retail
size fitting address those problems. The preview now makes any remaining
retail digits clear. Start with a transparent sheet, one fill and one
outline colour, and a margin. Check every digit before building.
