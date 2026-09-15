# Beta 70: replacing the HUD fonts and scorebug art by appending resources (Fable line 3, 2026-09-15)

Branch `fable/b70-assets` in `~/2k-worktrees/fable-b70-assets` (from `local/stack-beta-70` = df9b9dcf). Nothing pushed.
Noah's ask: "see if it can actually replace fonts and assets so instead of adding/working with what the game gave you,
you replace and inject successfully modernized ESPN assets". Answer: yes, through the game's own registry rules, with
no executable code changes. Everything below is proved offline under Unicorn with the game's own loader, registry and
boot code; nothing is witnessed in a played game.

## What is PROVED (native, `tests/mod_editor/test_nfl2k5_scorebug_assets.py`)

1. **The registry returns the most recently registered resource of a name.** Two FONT chunks named `font4` registered
   through the real relocator/registry (`0x43E30` -> `0x44B80`/`0x44B60`); the global lookup `0x449E0('FONT', "font4",
   ECX=0)` returns the second object. (`test_registry_returns_the_most_recent_resource_of_a_name`.) So an appended chunk
   with a retail name replaces the retail one for every lookup, without renaming or refitting the retail span.
2. **The boot sequence loads the font pack before the font table is filled.** `0x74A03..0x74A7E`: `0x43F50` constructs
   `global.iff` (0xE62ED0), `dir_ingame.iff`, `roster.iff`, `0x432F0` waits for the loader, then `0xEF5A0` ->
   `0xEF570` fills the ten-entry table at 0xA90ECC by global name lookup from the names at 0xA91928. Outer 3 of pack 0
   (identity 0x8EE9EEED, sector 416, 2,387,424 bytes) is `global.iff` (CRC32 of the uppercase UTF-16 name).
3. **A FONT named `FirstPersonComic` appended to global.iff is bound to slot 9 by the game's own boot loop.** The
   grown outer (retail bytes intact, one uncompressed FONT chunk appended, later outers' sectors shifted) loads through
   the native reader: 382 I/O completions, 137 TXTRs and 10 FONTs registered, the collection closes exactly at EOF.
   Then `0xEF570` fills all ten slots; slots 0..8 name font1..font9 in order and slot 9 names `FirstPersonComic`, and
   its descriptor is the appended chunk's object. (`test_boot_loop_binds_slot9_to_the_appended_font`.) Growth 75,776 B.
4. **An appended `font4` wins slot 3.** Same load with a second `font4` appended: the boot loop's slot 3 is the appended
   chunk, not the retail one, and slot 9 stays 0. (`test_boot_loop_binds_slot3_to_an_appended_font4_replacement`.)
5. **An appended 256x512 P8 `score_buga` wins the HUD lookup.** The grown gamedata.iff (outer 346) loads natively;
   `0x449E0('TXTR', "score_buga")` returns the last registered TXTR, whose name is `score_buga` and whose descriptor
   format word encodes 256 wide by 512 tall. (`test_hud_lookup_returns_the_appended_256x512_atlas`.) The retail
   material binding `FC1A0` uses this same lookup for every scorebug material, so the scene's materials bind the new
   atlas with no XBE change; normalized UVs address it as before (4x the texels per retail atlas region).
6. **Chunk builders round-trip** through the repo's decoders: the FONT chunk parses with `nfl_main_menu_font.parse_font`
   (name, ranges, 96-byte glyph records with 0xFF opaque words, texel-exact UVs, the retail 16-entry alpha palette
   tail, 256x256 established uniquely); the TXTR chunk parses as `score_buga` 256x512 P8. Pack growth keeps every
   retail byte and moves only later sectors (`test_grown_pack_keeps_every_retail_byte_and_moves_only_later_sectors`).
7. **The disc transaction** appends the grown pack 0 to a disposable copy, verifies the readback digest and switches the
   XDVDFS node with rollback (`test_apply_in_place_grows_pack0_and_switches_the_node`, retail XISO copy on Storage,
   deleted after).

Test run: `NFL2K5_RETAIL_INDEX=".../vc_53450030/0" PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_scorebug_assets.py -v`
(8 tests; the native ones take about three minutes; retail files, Unicorn and Pillow are precise SkipTests).

## What is built (`mod_editor/core/nfl2k5_scorebug_assets.py`)

- `espn_font_chunk(donor_span, FontSpec)`: a complete uncompressed FONT chunk from a retail donor (font8 or font4):
  UTF-16 name, designed metrics (`cap` in HUD units; line 1.29 cap; descent 0.33 cap), one codepoint range, glyph
  records for the broadcast-sampled ESPN glyphs (`data/nfl2k5_scorebug_assets/espn_glyphs.png` + `.json`: & 0-9 A D G L O
  d h n o r s t w) plus donor glyphs for the other requested characters (I c a e l), a fat dash for `~` (timeout marks)
  and a space; a 256x256 mask at one texel per HUD unit (`supersample` can raise the mask density, but then the repo
  parser's dimension proof no longer applies; the game does not care). 75,904 bytes resident.
- `texture_chunk(name, image, template)`: any power-of-two P8 texture on the retail `score_buga` descriptor template
  (name, palette offset, format word patched). `atlas_2026()` is a proposal for the 2026 look at 256x512 (top 256 rows:
  nine-slice pill tile with rounded caps and top lip, ESPN wordmark from the broadcast mask, a white-to-black wing ramp
  for material tinting, the light down plate and clock capsule; bottom 256 rows: the 32 current logos at 40 px in a
  6-column grid, `logo_uv(abbr)` gives each cell). 132,224 bytes resident (66,688 without the logo rows).
  The parent's mesh must use whatever UV regions the installed atlas has; `ATLAS_REGIONS` documents this one.
- `grow_pack(read, size, {outer: [chunks]})`: multi-outer growth over bounded views (no whole pack in memory).
- `apply_in_place(path, slot9=FontSpec(...), font4=..., font8=..., atlas=image)` and `image_status(path)`.
- `data/nfl2k5_scorebug_assets/`: the glyph sheet + boxes, the ESPN wordmark mask, 32 logos (ESPN CDN, 128 px), and
  `atlas_2026_preview.png`.

## What is NOT proved or not built (say so plainly)

- No played-game witness. Slot 9 binding, the appended atlas and the fonts are CPU-loader proofs.
- The glyph walk was not driven natively for the new font (the draw fixture needs the whole static capture); the chunk
  parses with the repo's strict FONT parser, which pins the same layout the native walker reads.
- `font4`/`font8` REPLACEMENT is proved as a mechanism only. The chunk the builder makes carries 33 characters and its
  own metrics; a shippable replacement of a retail font must carry every printable ASCII glyph with the retail advances
  and quads (font4 has 40+ HUD/menu call sites; font8 similar). That mode is a small extension (copy donor records,
  repaint cells) and was not built tonight. Until then, use slot 9 for the scorebug and leave font4/font8 retail (or the
  parent's in-place digit restyle).
- Scene growth (`score_bug` with more vertices and materials) was NOT built. It is feasible: every internal reference in
  the SCNE is a field-relative pointer (target = field + value - 1; the loader relocates generically): header +0x10 name,
  +0x14 object at 0x100; object +0x18/+0x20 -> materials at 0x1C0 (count 11 at +0x1C), +0x30 -> shape at 0x740; the
  shape references the transforms (+0x64 -> 0x1000) and the vertex streams (+0xD4 -> 0x2660 positions, +0xD8 -> 0x2D20
  colour/uv/palette); batch command blocks are referenced from records near 0x1D28. Growing needs: a re-serializer that
  recomputes every relative pointer, extended vertex streams, added 0x80-byte material records with names, and an
  encoder for the NV2A push-buffer batch words (`tools/nfl_static_gltf.decode_batches` is the decoder). Then the same
  append-and-win route replaces `score_bug` without touching the retail span. Estimated as the next job, not tonight.
- Resident memory: the retail chunks stay loaded beside the replacements (retail font4 17 KB, font8 66 KB, score_buga 5 KB
  decoded). Total added by slot 9 + the 256x512 atlas is 208 KB, well under the 0.4 MB that survived the intro in the
  Berman witness and a fifth of the 1.7 MB that crashed it.

## How the parent wires it

- Order with the runtime scorebug option: `apply_in_place` requires the RETAIL pack size; run it FIRST, or compose both
  growths in one pack rebuild (feed `compile_runtime_collection` a sliceable view of the grown pack). Its receipt has
  `pack_offset`/`pack_size`; `nfl2k5_scorebug_ingame.runtime_image_plan` currently accepts only retail or its own growth.
- XBE: to use slot 9, set the text records' font-slot field (+4) to 9 for the scorebug records the design wants in the
  ESPN face (scores 0xA9594C/0xA95984 +4, down text element 0xA959C8 +0xC, clocks 0xA958FC/0xA95924 +4, city records for
  the timeout dashes 0xA95884/0xA958AC +4); pure data edits, no code. `~` draws the dash.
- BuildPlan: an option such as `scorebug_assets: bool` (experimental, off in every preset) calling `apply_in_place` in
  the build after the pack-0 growth steps; registry row `nfl2k5.scorebug_assets` with the test file as its evidence;
  allowlist entries for the module, the test and `data/nfl2k5_scorebug_assets/**`.
- In-game checks for Noah: the scorebug text in the ESPN face (digits, & and st/nd/rd/th), the 40 px logos crisp, no
  missing glyphs in "4th & Inches"/"1st & Goal", the intro survives (memory), and the retail menus unchanged.
