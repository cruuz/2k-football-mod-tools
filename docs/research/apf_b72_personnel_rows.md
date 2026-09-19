# Per-book situation personnel rows, beta 72

Status: EXPERIMENTAL, off in every preset. Gameplay UNWITNESSED.

The book name is the resolved SPLB name, not the roster's display label. A
policy selects one of twelve actual down/distance buckets and a MASTER
personnel category. Its value is an ordinary comparison row, 0 through 10.
The requested row stays native and read-only. Removing an override returns
to the current shared MASTER row. This does not create formations or plays;
add the formation to the book first if it is absent.

The project stores `situation_personnel_row` requests with `book`, `key`,
`category`, and nullable `value`. Staging, Confirm all, undo, recipe replay,
project reload and build receipts use the existing CPU Play Calling event
transport. The shared enable switch controls both masks and row overrides.
No SPLB, MASTER or roster bytes change for a row-override request.

## Data format

The allocation remains `0x8462CA00..0x84630000`, exactly 13,824 bytes.
The big-endian header is magic `APF4`, version, book count, stride 268.
Version 2 retains the existing 28-byte ASCII book name and twelve 20-byte
formation masks in each book entry. Names are sorted and NUL padded.
The union of nonempty exclusion and row policies supplies up to 48 entries.

After those entries, version 2 appends a big-endian u32 override count and
four-byte records: book ordinal, live bucket, category ID, comparison row.
Records are sorted by book, bucket and numeric category, with no duplicates.
Remaining bytes must be zero. Capacity depends on book count: 235 overrides
with 48 books, or 2,446 with 15 books. A full allocation refuses staging
before anything is written. The reader checks count, ranges, canonical order
and padding, then re-encodes the complete allocation for exact comparison.

An omitted `personnel_rows` argument to the core encoder keeps version 1
bytes and code for compatibility with existing installed patches. New
Studio exports always pass a map and therefore use version 2, even when
empty. The canonical patch reader accepts both formats without weakening
its exact authored-code check. Unknown data versions bypass native policy
processing; the authoring reader refuses them.

## Native mechanism

The two exclusion draw hooks keep their pinned sites and behavior. Version
2 adds a hook at BASE `0x8486B090`, TU 1.1 `0x8486BD90`, replacing
`clrlwi r11,r11,26`. This is before the retail comparison-row arithmetic.
The leaf first performs the displaced instruction, then optionally changes
only r11 after matching scrimmage phase 4, automatic ordinary offense,
book name, live bucket and category. The original arithmetic computes the
curve and rating product, with its own rounding and installed curve values.
No curve rescaling or extra RNG draw is introduced. The leaf does not write
book or MASTER data. It preserves full-width GPRs, CR, FPRs and FPSCR.

All three leaves occupy 3,156 of the existing 3,328 executable bytes at
`0x84D0E300..0x84D0F000`. There are no new reservations. The two existing
24-byte draw receipts retain their layout and fallback meaning. If an
exclusion empties a draw, its original candidates and current row-derived
weights are retained. Rating 7 is a positive weight, not an exclusion.

## Fixture correction

The supplied diagnosis described Queens as retaining the 0.05 distance-curve
floor on 3rd-and-long. In the pinned O-ManBlock / MASTER fixture, Queens is
category 6 at stored row 7. At requested row 10 its curve term is 0.5, not
0.05. A gap of at least four yields 0.05. Setting its local row to 10 raises
its term to 1.0 without changing member ratings. The native matrix confirms
this calculation; the report does not treat the supplied floor as observed.

## Preview and witness boundary

Each candidate shows the personnel curve, mean of member formation ratings,
the f32 product used as the category weight, its category rank, the retail
weight and effective row. Categories may repeat across formation rows;
count each category once when summing category weights. The personnel draw
cubes these weights. Formation weights feed a separate subsequent draw.
The mean is computed over structural members before exclusions, as in retail.
The preview marks exclusions and empty-draw fallback. It remains a cold
model with neutral history, not a replay of the live RNG or learned history.

The page says the matching v2 patch must be installed and enabled. Its
inline status compares canonical exported bytes with the selected installed
patch. Editing or undoing a project cannot update an already running game;
install the new patch and restart Xenia. A global curve patch can further
change live curve terms; the standard preview uses the retail curve.

Witness scenario: resolved book O-ManBlock, ordinary CPU offense, first
quarter 15:00, tied score, midfield, 3rd-and-8, three timeouts. Set Queens
(category 6) to local row 10 in the over-7-yards third-down bucket. Keep
Pro: Strong (formation 14) unexcluded, set its three ratings to 7, and
exclude every other ordinary formation in that bucket. Confirm, build,
install the matching BASE or TU 1.1 patch, fully restart Xenia, and inspect
the call and personnel. Expected ordinary set: Queens / Pro: Strong.
Then remove the override and exclusions or move to another bucket to check
isolation. Only a player observing this in game can supply the witness.
