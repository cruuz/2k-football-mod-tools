# Beta 71: the 2026 scorebug's clock capsule in an ESPN-styled font (2026-09-15)

Branch `fable/b71-scorebug-font` (from `fable/b71-scorebug` at bcb0fcdf). EXPERIMENTAL / UNWITNESSED in a played game;
everything below is proved offline with the native renderer and the repo's decoders.

## What was wrong

The beta 70 capsule (81 x 19 HUD units) drew the quarter, the game clock and the play clock with the retail HUD glyphs
(12 units tall, 8 wide): "1ST" and the play clock digits overflowed their cells and the three read as one run.

## What ships

Two FONT resources appended to the HUD collection (outer 346), the way the beta 69 private fonts were built and bound
(those drew in game): the retail `font4` chunk copied whole under a new name, including the object tail the loader
fills at registration, every glyph record's advance and quad scaled, the clock characters' cells repainted from the
broadcast glyph sheet (`data/nfl2k5_scorebug_mnf/espn_glyphs.png`) at all sixteen alpha levels (the chunks are appended
uncompressed, nothing has to fit a fixed span).

| font | name (an existing UTF-16 literal, so the owner needs no new data) | scale (x, y) | digits | suffix | bound to |
| --- | --- | --- | --- | --- | --- |
| clock | `FirstPersonComic` (0xE6B490, the free tenth boot name) | 0.80, 0.92 | about 6.4 x 11 units | | game clock records 0xA958FC / 0xA95924 (descriptor at +0x1C: 0xA95918, 0xA95940), play clock (descriptor 0xA95A80) |
| quarter | `core_bug` (0xE6C79A, inside the retail "score_bug" literal) | 0.62, 0.72 | about 5 x 8.6 units | small st / nd / rd / th at the digits' scale | quarter record 0xA958D4 (descriptor 0xA958F0) |

The game uppercases the quarter literal before drawing ("1st" becomes "1ST"), so the capitals S, T, N, D, R and H carry
the small broadcast suffix (painted at the left of the cell; each record's UV cell and quad narrowed to the painted width,
so "1st" sets tight). Each chunk is 27,040 bytes (system 9,600, video 17,408: a 128 x 128 four-bit mask plus the retail
palette tail); the collection grows by 54,080 bytes to 402,560 (the beta 70 size class that passed the intro was
348,480; the beta 69 volume that froze was 1.7 MB).

Owner (`nfl2k5_scorebug_runtime`): after the displaced native `FC1A0` call has resolved every record's slot index into a
descriptor, setup looks each font up in the HUD collection (`0x449E0`, tag `FONT`, the literal name) and stores the
descriptor into the records' resolved-descriptor words (record +0x1C for the three text records, +0x48 for the play
clock record, whose callback sits at +4 and slot index at +8). A missing font leaves the retail descriptors alone. The
+4 / +8 slot indices are never written (the native init indexes the ten-slot table with them). The two lookups and
four stores cost 68 bytes; the cave allocator's reserved code page is exactly full at `CODE_SIZE` 1,408 (a 1,536-byte
request spills to the next code page past the data cave: "code page capacity exceeded; no unreserved page may be used",
and the standalone capacity test agrees), so the owner was shrunk instead of growing the allocation: the two per-side
timeout-dash writers became one shared routine with two five-byte entry stubs (the `dash_text0` / `dash_text1` labels and
the callback patches are unchanged), and the 40-entry plate colour table is packed to three bytes per entry with the
lookup forcing the alpha byte (`lea eax,[eax+eax*2]; mov eax,[eax+table]; or eax,0xFF000000`). The owner is 1,380 of
1,408 bytes; `CODE_SIZE`, the cave requests and the cave manifest are unchanged, so no manifest regeneration is needed
for this line.

Capsule cells (`nfl2k5_scorebug_exact.MNF_ANCHORS`, `atlas_mnf` separators at 18/64 and 50/64 of the tile): quarter
centred at source x 872 (cell 279.3..302 HUD), game clock centred at 963 (302..340), play clock at 1051 (340..360.7),
all on the capsule's vertical centre (`_ORIGIN(1008, 3, 15)`). Native renderer boxes: "1ST" 282.2..298.3 x 437.9..446.5
(core_bug), "13:10" 307.6..336.4 x 435.7..446.7 and "12" 344.6..356.4 (FirstPersonComic); containment failures none.
Renders: `/tmp/claude-1000/font_capsule_zoom3.png` (capsule at 5x), `/tmp/claude-1000/font_runtime.png`.

## Proofs

- `tests/mod_editor/test_nfl2k5_scorebug_fonts.py::test_beta71_runtime_binds_the_clock_fonts_and_keeps_the_native_score_fonts`:
  both fonts register without touching the global font table; the two clock descriptors and the play clock hold
  FirstPersonComic, the quarter holds core_bug, the score records keep font8; without the runtime fonts every record
  keeps a boot font.
- The native draw walk (`native_text_draw`) draws all three capsule rows with the new fonts (the first build from the
  asset-fork builder crashed the native draw on an unmapped read: its object lacked the retail tail; hence the donor copy).
- Suites (standalone, this worktree): see the commit message and `scratchpad/font/suites.log`; the two XBE gates run
  detached after the manifest regeneration (`scratchpad/font/gates.log`).

## Risks and what is not proved

- No played-game witness. The mechanism (appended FONT in the HUD collection, owner-bound descriptors) is the beta 69
  one that drew in Situation mode; the beta 70 in-place FONT4/FONT8 restyle that stalled the intro is not used.
- The play clock's descriptor word (+0x48) was identified by finding the init-resolved font4 object in the record and by
  the FONT8 override experiment; the retail rewrites the record's colour per frame, not its font.
- Advances are the retail font4 advances scaled by 0.80 (clock) and 0.62 (quarter); ESPN's letter spacing was not
  measured glyph by glyph.

## For the wings fork

The capsule tile separators moved (18 and 50 of 64); `MNF_ANCHORS` quarter/clock_a/clock_b/drop_clock changed; the
resources module gained `clock_font_spans`, `CLOCK_FONT_SPAN_SIZE` (54,080) and `CLOCK_FONT_SHA256`; `probe_sizes("mnf")`
and the compile append two FONT spans after the panels (the "mnf" appendix pin includes them); `CODE_SIZE` is 1,408 (the 1,536-byte request was rejected; see the owner-capacity explanation above).
