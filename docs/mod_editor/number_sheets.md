# Import number sheets 0-9

Choose the physical uniform set in Uniforms & Equipment, then Import number
sheet 0-9. Choose Jersey, Helmet, or Arm / shoulder, Detect layout from image, and Match
retail size. The original game uses different sizes and different compressed
budgets for individual digits, even within the same uniform.

Use a PNG with a transparent background and the ten digits in order, 0 to 9.
Leave out labels, guides and outside borders. These four layouts work:

| Layout | Order | Size with 64x64 cells |
| --- | --- | --- |
| One row | 0 through 9 from left to right | 640x64 |
| One column | 0 at the top, 9 at the bottom | 64x640 |
| Five columns, two rows | 0-4 above 5-9 | 320x128 |
| Two columns, five rows | 0 1, then 2 3, through 8 9 | 128x320 |

Larger cells work the same way, for example 640x256 for a 0-4 over 5-9 sheet of 128x128 cells.

## The layout is found from the sheet

Detect layout from image does not need exact textbook sizes. It tries three things, in order,
and the preview says which one it used:

1. **Equal square cells** that divide the sheet exactly (the table above at any scale).
2. **Equal cells at rounded cut lines**, for sheets that do not divide evenly. A 1024x512
   canvas holds five columns of 204.8 pixels, so the cuts fall at 205, 410, 614 and 819. This is
   only used when every cut falls between two digits, so no digit is ever sliced.
3. **The digits' own positions**, for sheets with margins, gaps of different sizes, tall or wide cells,
   or digits of different widths laid out like typed text. The Studio finds the rows and the digits
   in each row from the transparent gaps and puts each digit in a cell of its own.

If you choose a layout yourself, that choice is honoured. When most of its cell borders would slice
through digits, and the digits clearly sit in another layout (a 0-4 over 5-9 sheet whose width happens
to divide by ten, picked as One row), the import is refused and names the layout that fits.

A sheet is refused, with what it saw and how to fix it, when:

- the digits touch or overlap, or there are labels or marks between them: the message says how many separate
  shapes it found in each row and shows the sizes that work;
- the sheet is not a picture the Studio can read, is empty, larger than 128 MiB, or over 16 million pixels
  (1024x1024 cells fit; the message gives the actual size);
- the picture has no transparent pixels at all (a JPEG or a flattened PNG): every digit would become a solid block;
- a chosen layout cannot cut the sheet without slicing a digit, with the nearest canvas size that would work.

A single empty cell among the ten, or a digit with no transparent pixels, is flagged in the notes on that digit.

## Colours, gradients and the size of each slot

Every digit has its own small compressed slot, and the slots differ a lot. Across the 634 uniform sets
a jersey digit's slot holds between 544 and 3,312 bytes, and about a third of the sets average under 1,200.
Tight and roomy slots are mixed through every kind of set (about 2 in 10 alternates, 3 in 10 current
uniforms and 4 in 10 throwbacks average under 1,200 bytes), so the preview for the set you import into
is the guide. Example, the Rams: the 1965-1999 home and away sets hold 640 to 1,280 bytes per digit,
the current and 2000-2004 sets 1,088 to 2,320. In the tight sets checked (the Rams 1998-1999 and the
Steelers 1968-1976), the original digit is one flat colour, so the slot is sized for a one-colour number.

A flat fill with one outline colour fits most slots, and one flat colour fits the smallest. Shading costs space:

- A gradient (for example the 2020 Rams numerals, gold at the top fading to white) fits the roomy slots as drawn.
- In a slot that is too small, the Studio tries gentler versions of your digit before it gives up, and it
  never drops the outline or the fill. In order: first, for a digit made of flat colours that picked up stray
  in-between colours when the sheet was scaled down, those strays are merged back into its own fill and outline
  colours; then hard edges at the largest size (the smaller views keep soft edges, like many original digits);
  then, for a digit with real shading, the shading reduced to four, three and two flat colours, and, for a
  numeral that is nothing but shading with no outline, one flat colour. The notes for that digit say which one
  was used, for example "its shading was reduced to 3 flat colours, with hard edges".
- Trying these versions takes a few seconds per digit, so a sheet with many tight slots can take a minute to preview.
- If even the simplest version does not fit, that digit keeps the original number, the preview marks it
  KEPT RETAIL, and the note gives the numbers: how many bytes the simplest version needs, how many the
  slot holds, and how many colours the digit used. The notes also list the space each digit used.

To get a shaded or outlined numeral into a tight set, use one flat colour there, or import it into a set
whose slots are bigger.

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
premultiplied colour before saving ordinary straight alpha. Resizing keeps each
colour channel inside the range your art uses: a resize filter overshoots past a
flat colour, and that used to turn a royal blue outline a shade darker and make a
flat two-colour numeral look like a many-colour one that needed more room. It
extends edge colours into invisible pixels so filtering cannot pull in
transparent black.
Every smaller texture level is rebuilt with a clear border, matching the
retail mip margins, and all levels share one palette.
The receipt records the box, scale, cleanup and selected palette.

The encoder first tries the usual palette budgets down to 16 colours. Clean
one-fill, one-outline art can also try 12 and 8 colours while keeping both
regions. Match retail size may then try an additional 6% or 12% reduction.
It does not erase an outline or accept a one-colour version of a two-colour
number to force a fit. Only then does it use the simplifications above.
A digit that still cannot fit stays retail.

In the preview, each top sample is what the build will write and each bottom
sample is the original retail digit at the same level. KEPT RETAIL marks a
fallback beside the digit. The Import button counts the outcome, for example
Import 7 digits, 3 kept retail, and is switched off when none of the ten
would change. The 57 pair and small size views estimate how
the digits look together. They do not reproduce camera perspective or jersey
lighting. Inspect every row and the notes before accepting.

The ten cells stage together through Team Kit as one Undo action. Check my
images and the build use the same encoding policy and say which digits will
stay retail. Load the game source so Check my images can measure the original
registration. Save the project and include its edits in the build. Verify
front, back, shoulder and helmet numbers in play, both up close and from the
broadcast camera. In-game appearance remains UNWITNESSED until played.

Other equal cell sizes also work. The source must be a regular file no larger
than 128 MiB or 16 million pixels.

## Why did some digits stay old, look larger, or bleed?

Each digit has its own small compressed slot. A noisy number can fit one
slot and overflow another, which kept the original digit and made the set
look mixed. Filling the whole cell also makes a number wider than the
original. An opaque edge can smear when the game samples past the cell,
and transparent black can darken a soft edge. The new cleanup and retail
size fitting address those problems. The preview now makes any remaining
retail digits clear. Start with a transparent sheet, one fill and one
outline colour, and a margin. Check every digit before building.
