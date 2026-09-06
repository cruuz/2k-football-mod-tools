# MVP Baseball 2005 (PlayStation 2) — the module

**What this document is.** `mod_editor/games/mvp05_ps2/` is the fourth game
on the Game Studio shell and the first that is not a Tiburon disc: no `TERF`
container, no `TDB` database, every asset inside one of 211 EA `BIG`
archives and every texture an `SHPS` bank [M]. `MVP05_PS2_MODULE_PLAN.md` is
the plan this was built from and keeps its measurements; where the two differ,
this document is current. The formats are `EA_BIG_FORMAT.md`,
`EA_SHPS_FORMAT.md` and `EA_SCHL_FORMAT.md`; the CSV tables are described in
`mod_editor/games/_formats/ea_csv_db.py` itself.

**Evidence tags.** **[M]** measured on the retail SLUS-21135 disc this box
holds, read-only; **[S]** sourced; **[A]** assumed.

**Retail-free.** Counts, names, offsets, lengths and digests. No cell value,
string, pixel, sample or palette entry from the disc is in this repository.

---

## 1. The verdict, in six sentences

1. **All fourteen pages are answered**: eight writers at
   `offline-writer-proved`, one export lane at `extract-only`, four
   inventories at `read-only-mapped`, and one page note each for the three
   pages the disc gives nothing to write (§3).
2. **The wall in the plan's §6 came down.** A RefPack encoder
   (`ea_big.refpack_compress`) packs every entry measured smaller than EA's
   own stream — by 10 bytes to 8,687 — so a bounded rewrite inside the slot an
   entry already owns (`ea_big.rewrite_entry`) is a real writer, and eight
   lanes end in it or in the loose-file writer [M].
3. **The second wall, `SHPS` code `0x0E`, is half down.** It is a 4×4-block
   codec over the attached 256-entry palette — two 8-bit endpoints per block
   whose layout and block map are decoded (a flat-endpoint render shows the
   picture) and 2-bit per-pixel selectors whose semantics are not, after every
   reading tried in a bounded hour. The kits, faces and field art therefore
   stay listed, not drawn (§5).
4. **Every writer is proved twice offline** — on the synthetic disc in CI and
   on the retail disc by hand, chained so the last image carries every edit
   (§4) — and **no rebuilt image has been booted**; every receipt says so.
5. **PCSX2 identities are derived, none confirmed**: 8-bit images with a
   256-entry palette get names computed from their own bytes through the
   shared `pcsx2_texture_name`; no texture dump of this game exists here.
6. **A second EA `BIG` title costs its page groupings and its identity**
   (§8); the readers, the encoder, the slot writer and the four lane classes
   are shared already.

---

## 2. What the module is made of

| file | what it holds |
|---|---|
| `containers.py` | the identity digests, which archive feeds which page, the disc opened in place, and every synthetic builder |
| `disc_identity.py` | `Mvp05DiscIdentifier`: SLUS-21135, one boot-ELF digest, `unknown edition` for anything else |
| `disc_write.py` | the one way anything is written: `tools/ps2_iso9660_writer.py` in, `tools/ps2_iso9660_verify.py` out |
| `database_lane.py` | `CsvTableLane`, three rows: rosters, team identity, tuning |
| `loch_text.py`, `loch_lane.py` | the `LOCH` string file, measured and written; the UI-strings row |
| `art_lane.py` | `ShpsArtLane` (three writer rows) and `ShpsBankLane` (three `0x0E` inventories) |
| `audio_lane.py` | the stream lane (play, export, replace in a bare file) and the bank lane (export) |
| `inventory_lane.py` | every bank on the disc, one row per archive |
| `validators.json`, `tools/validate_mvp05_ps2_*.{sh,bat}` | five validators through `tools/validate_game_lane.py` |
| `tests/mod_editor/test_mvp05_ps2_lanes.py`, `..._module.py` | 20 tests on the synthetic disc, plus the conformance harness |

Shared code this module added: `ea_big.refpack_compress`, `ea_big.rewrite_entry`
and `BigArchive.row_offset`; `ea_shps.encode_indexed` and `ea_shps.replace_pixels`;
`mod_editor/games/_formats/ea_csv_db.py`. `ea_big.py`, `ea_shps.py` and
`ea_csv_db.py` joined the release allowlist and the runtime closure, which is
where the plan's §8 said they belonged once a shipped module imported them.

---

## 3. The fourteen pages

| page | lane (row) | classification | what it writes, or why not |
|---|---|---|---|
| Uniforms & Equipment | `uniforms.kit_banks` | `read-only-mapped` | lists every kit image of `UNIFORMS.BIG` and `COOPUNIS.BIG`; all `0x0E`, §5 |
| Names, Numbers & Faces | `rosters.database_tables` | `offline-writer-proved` | any cell of the 18 `DATABASE.BIG` tables, re-packed into its slot |
| | `rosters.face_banks` | `read-only-mapped` | lists `PORTRAIT.BIG` and `GHEAD.BIG`; all `0x0E` |
| Text & Team Identity | `identity.team_tables` | `offline-writer-proved` | any cell of `team.dat`, `org.dat`, `tstat.dat`, `manager.dat` |
| | `identity.ui_strings` | `offline-writer-proved` | any of the 7,977 `LOCH` strings, inside its span |
| Field Art & Create-Team Art | `field_art.banks` | `read-only-mapped` | lists `FIELDS.BIG` and the 7 ballpark-builder archives; all `0x0E` |
| Stadiums | `stadiums.park_textures` | `offline-writer-proved` | 8-bit images of the 87 park archives and the park menu art, exported and written back |
| Presentation | `presentation.overlay_textures` | `offline-writer-proved` | 8-bit images of `IGONLY`, `COOPOV`, `HRSONLY`; the `.fel` scripts listed, not parsed |
| Menus & UI | `menus.widget_textures` | `offline-writer-proved` | 8-bit widget images written back; `0x05` logos export; 59 loading screens listed |
| The Crib | — | page note | not an MVP concept |
| Audio | `audio.streams` | `offline-writer-proved` | EA-XA streams played, exported, and replaced in the 31 bare files; MicroTalk refused by name |
| | `audio.banks` | `extract-only` | the two `BNKl` banks exported |
| Gameplay | — | page note | boot ELF measured; no patch site located, no community pnach known |
| Playbooks & Plays | `playbooks.tuning_tables` | `offline-writer-proved` | the tuning CSVs (`PROGRESS`, `ROOKIE`, `SCHEDULE`, the audio event tables) |
| All Textures | `textures.bank_inventory` | `read-only-mapped` | every bank in every archive, one row per archive |
| Saves | — | page note | a save is not the disc |
| Build & Share | — | the shell's own | — |

Every page note is one sentence in `game.json`, and every one states a
measurement rather than a plan.

### 3.1 The tables (three rows, one class)

The disc's rosters are text in EA's numbered-field grammar — `<id>,0 v,1 v,…,;`
CRLF — and its tuning is plain CSV [M]. A cell edit re-renders one line, the
table is re-packed with RefPack when the disc packed it, and the stored bytes
go back **inside the slot the entry already owns**: the archive's length,
every other row and every other payload keep their bytes, and the row's size
word is the only other change. The slot on this disc is the entry's stored
size plus 0 to 3 bytes [M], so the whole writer rests on one measurement:
with the default chain depth the encoder packs every one of the 18 tables
**smaller** than EA's stream (`EA_BIG_FORMAT.md` §3.3). A table that no longer
fits once re-packed — random text in every row will do it — is refused
naming the byte count, and the tests prove that refusal.

`check_edit` refuses a comma, a line break, non-Latin-1 text, and a
non-number in a column that held a number. Adding or removing a row is
outside the bound and is not offered.

### 3.2 The strings

`LOCH` was measured here (`loch_text.py`): a 20-byte header naming the
`LOCL` offset, a `LOCI` table of `(u16 id, u16 index)` pairs, and a `LOCL`
chunk of `u32` offsets followed by UTF-16LE NUL-terminated strings [M]. A
string's span runs to the next offset in address order; a replacement must
fit it with its terminator and is NUL-padded to it. The file is loose on the
disc, so the writer is the ISO writer alone.

### 3.3 The art (three writers, three inventories, one walker)

One walker parses every bank of a page's archives and lists every image with
its size, code, palette width, mip bytes, packing and slot. A writer lane
adds `decode_png` (any decodable image), `encode` (an 8-bit PNG of exactly
the image's size, indexed against the image's own palette — exact matches
counted, the nearest entry otherwise), `replacement_identity` (derived), and
a build that swaps the level-0 pixel bytes inside the bank at the same size,
re-packs the bank into its entry's slot and puts the archive back inside its
extent. Direct-colour (`0x05`) images export and are not written: no encoder
for that code is offered, and the refusal says so. The three inventory lanes
are the same walker over archives that are entirely `0x0E`, with the
measured refusal on every row.

### 3.4 The audio

The 31 bare `SCHl` files are whole ISO9660 files [M], so a replacement is
the cheapest writer on the disc: mixed and resampled to the stream's own rate
and channels, encoded as EA-XA with the shared `ea_schl.build_stream`, it
must fit the bytes the stream occupies and is zero-padded to them. The
verifier re-walks every stream of the file out of both images, requires every
untouched one byte-identical, and decodes the replaced one against the WAV it
came from (≥ 12 dB). The 9,123 archived speech entries and the two
commentary containers are MicroTalk and are listed with their rate, channels
and length and refused by name.

---

## 4. The real-disc trials [M]

Read-only source, scratch destinations, chained so each image carries every
edit before it, each verified against its own source, every image deleted
afterwards. Every edit is a value this project chose — a fixture name, a
fixture string, diagonal bands of the image's own palette, a synthetic tone —
so any pixel or byte difference would be the writer's.

| lane | what was written | ranges / declared bytes | verdict | catalogue / build / verify s |
|---|---|---:|---|---:|
| `rosters.database_tables` | `DATABASE.BIG!attrib.dat` line 1: 751,834 plain → 176,947 stored in a 185,628-byte slot (re-packed; was 185,628) | 2 / 1,010,686 | PASS | 2 / 224 / 57 |
| `identity.team_tables` | `DATABASE.BIG!team.dat` line 1: 38,323 plain → 6,107 stored in a 6,440-byte slot (re-packed; was 6,439) | 2 / 1,010,686 | PASS | 0 / 203 / 78 |
| `playbooks.tuning_tables` | `PROGRESS.BIG!stadium.csv` line 1: 1,675 plain → 1,675 stored in a 1,676-byte slot (stored; was 1,675) | 2 / 17,856 | PASS | 4 / 71 / 10 |
| `identity.ui_strings` | `FEENG.LOC` string 0, span 26 bytes at +50,868 | 2 / 415,516 | PASS | 1 / 90 / 6 |
| `stadiums.park_textures` | `A001DAY.BIG!cram.ssh` image 1, 64x32, 2,048/2,048 exact; bank 832,160 → 548,715 stored in 551,016 (was 551,013) | 2 / 2,144,689 | PASS | 43 / 66 / 5 |
| `presentation.overlay_textures` | `IGONLY.BIG!ingameov.ssh` image 15, 64x32, 1,436/2,048 exact; bank 123,712 → 48,340 stored in 49,896 (was 49,893) | 2 / 114,474 | PASS | 0 / 99 / 36 |
| `menus.widget_textures` | `FEONLY.BIG!sdoodads.ssh` image 0, 128x32, 3,840/4,096 exact; bank 358,304 → 156,927 stored in 158,444 (was 158,444) | 2 / 523,012 | PASS | 6 / 90 / 5 |
| `audio.streams` | `BATDIT.AST` stream 0: 68,908 encoded, padded to 324,156; 64,000 samples at 32,000 Hz × 2 | 2 / 26,717,064 | PASS | 1 / 68 / 9 |

The declared bytes are the ISO writer's own accounting: the whole extent of
the rewritten file plus its 8-byte directory-record length, which is a
superset of the two ranges the archive writer changed (a size word and one
entry's span; the receipt names both). Build time is the 4.3 GB copy; the
edit itself is seconds. The audio step's 26.7 MB is `BATDIT.AST`, the first
bare stream file in path order.

Every destination is 4,300,275,712 bytes, the length of the source. The
independent verifier ran three checks on each: `tools/ps2_iso9660_verify.py`
re-derived every declared range with its own ISO9660 decoder and compared
every byte outside them; the lane re-read the archive (or file) out of both
images and compared every untouched entry byte for byte; and the edited
content was re-derived from the recipe and compared with what the new image
holds.

### 4.1 The catalogues [M]

Every number from `python -m mod_editor.games.mvp05_ps2.<lane> --source <iso>` over the
retail disc, wall clock on this box, pure Python:

| lane | what it walked | images / rows / strings | decodable / editable | seconds |
|---|---|---:|---:|---:|
| `rosters.database_tables` | `DATABASE.BIG`, 18 tables | 33,808 rows | all; 3,000 listed | 4 |
| `identity.team_tables` | `team.dat` 126 × 55, `tstat.dat` 126 × 5, `org.dat` 34 × 14, `manager.dat` 34 × 21 | 320 rows | all | <1 |
| `playbooks.tuning_tables` | 5 archives, 76 tables (8 stored, 68 packed) | 26,052 rows | all; 3,000 listed | <1 |
| `identity.ui_strings` | `FEENG.LOC` 6,352, `IGENG.LOC` 1,584, `MC_ENG.LOC` 41 | 7,977 strings | all; 4,000 listed | 1 |
| `stadiums.park_textures` | 87 park archives + `STADIUMS.BIG` + `COOPSTAD.BIG`: 2,284 banks | 12,846 images | 10,182 decode (`0x02`); 8,305 carry a derived PCSX2 name; 2,664 are `0x0E` | 51 |
| `presentation.overlay_textures` | `IGONLY`, `COOPOV`, `HRSONLY`: 9 banks; 88 `.fel` scripts listed | 322 images | 272 decode; 40 named; 50 `0x0E` | <1 |
| `menus.widget_textures` | 17 menu archives + `LOGOS.BIG` + 59 loading screens: 424 banks | 2,400 images | 1,145 `0x02` decode and write; 396 `0x05` export; 859 `0x0E` listed | 6 |
| `uniforms.kit_banks` | `UNIFORMS.BIG` 555 banks, `COOPUNIS.BIG` 124 | 986 images | 0: 555 `0x0E`, 431 `0x01` 1×1 stubs | 1 |
| `rosters.face_banks` | `PORTRAIT.BIG` 2,391 banks, `GHEAD.BIG` 8,400 | 10,791 images | 0: all `0x0E` | 65 |
| `field_art.banks` | `FIELDS.BIG` + 7 ballpark-builder archives: 224 banks | 224 images | 0: all `0x0E` | <1 |
| `audio.streams` | 31 bare `SCHl` files; 12 archives (9,123 `SCHl` entries) | 4,833 streams + 9,123 entries | 4,819 EA-XA decode and are replaceable; 14 + 9,123 MicroTalk refused | 6 |
| `audio.banks` | `PAUSESFX.BNK` 5 sounds, `ZSNDFRNT.GEN` 6 | 11 sounds | 10 export (one declares no rate) | <1 |
| `textures.bank_inventory` | 211 archives, 643 nested, 16,371 banks | 59,035 images | 34,650: `0x02` 34,242, `0x05` 408; refused `0x0E` 23,954, `0x01` 431 | 62 |

Two corrections to the plan's numbers: the disc holds **59,035** images in
its 16,371 banks (the plan's 27,485 was a 4,665-bank sample), of which
**23,954** — 41% — are `0x0E`; and the face archives hold 10,791 images, not
banks and images in equal number by coincidence: every face bank is one
image.

The stadium lane's 51 seconds is 2,284 RefPack decodes plus a PCSX2 name
derivation for each of 8,305 images; the face lane's 65 is 10,791 decodes
of banks that are then refused. Both run in a child process behind the
studio's progress line.

---

## 5. `SHPS` code `0x0E`: the verdict

Every kit, portrait, head texture, loading screen and piece of field art on
the disc is code `0x0E`. The bounded hour the brief allowed established what
it is and stopped short of drawing it; `EA_SHPS_FORMAT.md` §5 carries every
measurement and every rejected reading. In short:

- it is **not** an opaque compressed codec: the payload is `w*h*3/8` bytes of
  8-bit palette indices and 2-bit selectors, and the 256-entry palette that
  follows every block is used by them (246–252 distinct entries, 254–256
  byte values in use);
- the **endpoint stream** (first `w*h/8` bytes) is decoded: one 32-bit word
  per two adjacent blocks, `[i1(x), i1(x+1), i0(x), i0(x+1)]`, block-raster
  order — a flat render of every block in its `i0` colour is a recognisable
  quarter-resolution portrait and loading screen;
- the **selector stream** (last `w*h/4` bytes) is 8 bytes per pair of blocks
  in raster order with bit-planar nibbles, and **its per-pixel semantics are
  not decoded**: row-per-byte, u32, 16-bit planes, nibble-interleaved and
  bit-planar readings × both bit orders × all 24 weight orderings all leave
  noise inside the blocks;
- the four 48-bit decompositions suggested afterwards — two RGB565 endpoints
  with 1-bit indices, an RGB565 base with 2-bit luma steps, interleaved CLUT
  pairs with 2-bit selectors, and 8×8-tile block order — were each rendered
  against a portrait and scored worse than the two-stream reading (135.5,
  97.8, 69.9 and +1.9 against 14.5).

So those pages are `read-only-mapped` with that reason, and the reader hands
back nothing rather than a half-right picture. Whoever picks it up starts at
the selector semantics with the block map, the endpoint order and the raster
order settled.

---

## 6. What still needs a boot

Nothing above says the game loads any of it. `EA_BIG_FORMAT.md` §7 still
holds: no checksum was found in any archive, and that negative is only as
good as the search, because **no archive rebuilt by this project has ever
been loaded by any game**. The owner does this on the rig with an image built
by these lanes; the trial in §4 is the recipe:

1. **The rosters.** The edited player's first name in `attrib.dat` row 1
   should read in any roster screen. A disc that hangs at the first roster
   load names the archive writer, not the game.
2. **The strings.** The edited `FEENG.LOC` string is a front-end string; the
   catalogue's LOCI ids say which.
3. **The art.** Diagonal bands in a park texture, an overlay texture and a
   menu widget.
4. **The audio.** A two-second tone where a crowd bed was.
5. **The negative that matters.** The game must still *load*. A rewritten
   size word in an archive's table is the step most likely to be checked.

Until those are recorded every writer row stays `offline-writer-proved` and
every receipt keeps the sentence that says so.

**Also unproved, and not on the boot list:** whether PCSX2 loads a pack built
from the derived names — no dump of this game exists, so no name is confirmed.

---

## 7. Verifying this document

```bash
export QT_QPA_PLATFORM=offscreen
python -m mod_editor.games conformance --game mvp05_ps2          # 453 of 453
python tools/validate_game_lane.py --game mvp05_ps2 --all         # five PASS tokens
PYTHONPATH=. python tests/mod_editor/test_mvp05_ps2_lanes.py
PYTHONPATH=. python tests/mod_editor/test_ea_big.py tests/mod_editor/test_ea_shps.py
```

The disc numbers are reproduced by `python -m mod_editor.games.mvp05_ps2.<lane> --source <iso>`
for each lane module; each prints one line of counts and writes the
catalogue document with `--out`.

---

## 8. What a second EA `BIG` title costs

NBA Street Vol. 2 or FIFA Street 2 on the PS2 are the same container family:
`BIG` archives, `SHPS` banks, `SCHl` audio, and — in EA's non-Tiburon studios
of that era — text tables of one shape or another. After this module the
readers, the RefPack encoder, the slot writer, the `SHPS` 8-bit writer, the
`LOCH` reader and the four lane classes (`CsvTableLane`, `UiStringsLane`,
`ShpsArtLane`/`ShpsBankLane`, `AudioStreamsLane`/`AudioBanksLane`) are shared
or one import away. A second title costs:

1. a `containers.py` — the identity digests and which archive feeds which
   page, measured with the census the readers already ship (a day);
2. whichever of its tables are **not** CSV: a game that keeps rosters in a
   binary table needs a reader for it, which this module did not need;
3. its own `0x0E` share: the same codec, the same half-decoded state, and the
   same read-only rows until the selectors are decoded, which is one piece of
   work that lifts every EA `BIG` title at once;
4. `.fel`/`.apt` layout scripts if its menus matter, which no module parses;
5. registry rows through `tools/registry_add_rows.py`, a synthetic disc, and
   the same real-disc trial.

The pieces that were genuinely new here — the encoder, the slot writer, the
CSV model, the `LOCH` reader and the bit-exact art round trip — do not have to
be built again.
