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

1. **All fourteen pages are answered**: nine writers at
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
   reading tried in a bounded hour. The faces and field art therefore stay
   listed, not drawn (§5).
3a. **The uniform page went past that wall without decoding it.** The kit a
   player *wears* is not in the archives named `UNIFORMS` — those are preview
   swatches — it is in `MODELS.BIG`, and **21,767 of its 30,535 images are
   ordinary 8-bit `0x02`** that `ea_shps` has decoded and encoded all along
   (§9). `uniforms.kit_textures` writes them: the low-detail whole kit, caps,
   helmets, gloves, sleeves, wristbands and every one of the 16,110 letters and
   digits the game composites into a nameplate. The high-detail jersey and the
   trousers are the `0x0E` half and stay refused, so this is a kit editor with
   a named hole in it, not a complete one.
4. **Every writer is proved twice offline** — on the synthetic disc in CI and
   on the retail disc by hand, chained so the last image carries every edit
   (§4) — and **no rebuilt image has been booted**; every receipt says so.
5. **PCSX2 identities are derived everywhere and confirmed where a dump
   reached**: 8-bit images with a 256-entry palette get names computed from
   their own bytes through the shared `pcsx2_texture_name`, and a three-frame
   PCSX2 dump now confirms **1,008 of them** by exact pixel equality — 76
   distinct pictures, mostly one park texture shared across many ballparks
   (§4.2). The pairing also found the deriver was wrong for one whole class of
   draw and fixed it, and it settled the `0x0E` question the only way ground
   truth can: there is no decoded `0x0E` texture in the dump (§5).
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
| `art_lane.py` | `ShpsArtLane` (four writer rows) and `ShpsBankLane` (three `0x0E` inventories); the `MODELS.BIG` bank-family rule, the per-part census and the slot-fit census (§9); also the PCSX2 identity table it loads and the sentence each texture gets |
| `tools/mvp05_ps2_texture_identities.py` | pairs a PCSX2 texture dump with the disc on exact pixels and writes the three measured documents (§4.2); `--selftest` proves it on a synthetic bank |
| `audio_lane.py` | the stream lane (play, export, replace in a bare file) and the bank lane (export) |
| `inventory_lane.py` | every bank on the disc, one row per archive |
| `validators.json`, `tools/validate_mvp05_ps2_*.{sh,bat}` | five validators through `tools/validate_game_lane.py` |
| `tests/mod_editor/test_mvp05_ps2_lanes.py`, `..._module.py`, `..._identities.py` | 20 tests on the synthetic disc, 13 on the identities, plus the conformance harness |
| `docs/product/measured/mvp05_ps2/models-big-parts.json` | the `MODELS.BIG` census: every bank with its family, every part tag with its codes and sizes, and the slot-fit measurement (§9) |

Shared code this module added: `ea_big.refpack_compress`, `ea_big.rewrite_entry`
and `BigArchive.row_offset`; `ea_shps.encode_indexed` and `ea_shps.replace_pixels`;
`mod_editor/games/_formats/ea_csv_db.py`; and, from this pass,
`pcsx2_texture_name.PSMT8H` with the linear hashed stream and
`derive_names(..., extra_psms=...)` (§4.2). `ea_big.py`, `ea_shps.py` and
`ea_csv_db.py` joined the release allowlist and the runtime closure, which is
where the plan's §8 said they belonged once a shipped module imported them;
`pcsx2_texture_name.py`, `xxhash3_64.py`, the identity tool and the three
measured documents joined them when the identity table became something the
art lane reads at catalogue time.

---

## 3. The fourteen pages

| page | lane (row) | classification | what it writes, or why not |
|---|---|---|---|
| Uniforms & Equipment | `uniforms.kit_textures` | `offline-writer-proved` | the kit a player wears: 21,767 8-bit images of `MODELS.BIG`, exported and written back; its 8,756 `0x0E` parts listed, §9 |
| | `uniforms.kit_banks` | `read-only-mapped` | lists the 986 uniform *preview* images of `UNIFORMS.BIG` and `COOPUNIS.BIG`; all `0x0E` or 1×1 stubs, §5 |
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

### 3.3 The art (four writers, three inventories, one walker)

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
| `uniforms.kit_textures` | `MODELS.BIG!u010a.ssh` images 0 (`llod`, 128x128) and 5 (`hat`, 128x64) and `!f010a.ssh` image 0 (`A___`, 16x32); banks 255,264 → 194,450 stored in 216,124 (was 216,124) and 75,552 → 18,642 stored in 19,304 (was 19,302) | 4 / 122,887,433 | PASS | 233 / 79 / 33 |
| `audio.streams` | `BATDIT.AST` stream 0: 68,908 encoded, padded to 324,156; 64,000 samples at 32,000 Hz × 2 | 2 / 26,717,064 | PASS | 1 / 68 / 9 |

The kit row is the trial this pass added, and it is deliberately three
textures in two banks of one archive so the multi-image and multi-bank paths
are both exercised: 25,088 pixel indices re-derived, **both banks the exact
length they went in**, **0 bytes of either bank changed outside the edited
pixels**, the other 2,503 entries of `MODELS.BIG` byte-identical, and 233,494
bytes of the 4.3 GB image different, every one inside the declared span. Its
first two images are two of the 167 `MODELS.BIG` textures a PCSX2 dump
confirms (§4.2), so what was written is art the emulator has been seen
drawing. The two edited banks were chosen for headroom, which is the writer's
real bound: **1,381 of `MODELS.BIG`'s 1,407 banks re-pack inside their own
slot unedited, with a median 39 bytes to spare** (§9.3), and an edit that
compresses worse than the pixels it replaced is refused naming the byte count.

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
| `uniforms.kit_textures` | `MODELS.BIG`: 1,407 banks (436 kit, 467 lettering, 504 head) beside 549 `.ord`/`.orl` pairs | 30,535 images | 21,767 `0x02` decode and write; 21,363 carry a derived PCSX2 name and 167 a confirmed one; 8,756 `0x0E` and 12 `0x05` listed | 232 |
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

### 4.2 PCSX2 replacement identities: what three frames reached [M]

A replacement filename is `<tex0 hash>-<clut hash>-<bits>.png` and both hashes
are computed by the emulator at draw time, so no disc file carries one. Two
things can produce it: `pcsx2_texture_name` **derives** it from the texture's
own bytes, and `tools/mvp05_ps2_texture_identities.py` **confirms** it by
pairing a texture dump with the disc on **exact pixel equality**, RGBA with the
CLUT's own 0..128 alpha and no tolerance at all.

The corpus is the one that exists: **three single-frame GS dumps of one
Cardinals half-inning at Fenway** — two batting frames and a batter
introduction card — replayed headless with texture dumping and
`ClassicTextureNames` on. 1,308 dumped files; **228 of them equal a disc image
exactly**, and because parks share art those 228 identify **1,008 disc images
carrying 76 distinct pictures**. 988 of the 1,008 share their picture with at
least one other image, which is not an ambiguity the emulator has — PCSX2
hashes pixels, so one replacement file covers every one of them — and each
identity records how many others it shares with.

| page (archives) | images | of them `0x0E` | derived name | **confirmed** | frames that drew one |
|---|---:|---:|---:|---:|---:|
| `stadiums.park_textures` (87 parks + 2) | 12,846 | 2,664 | 8,305 | **816** (59 pictures) | 3 of 3 |
| `menus.widget_textures` (17 + logos + 59 loaders) | 2,400 | 859 | 317 | **13** | 3 of 3 |
| `presentation.overlay_textures` (3) | 322 | 50 | 40 | **10** | 3 of 3 |
| `uniforms.kit_textures` (`MODELS.BIG`) | 30,535 | 8,756 | 21,363 | **167** | 3 of 3 |
| `uniforms.kit_banks` (2) | 555 | 555 | 0 | 0 | none |
| `rosters.face_banks` (2) | 10,791 | 10,791 | 0 | 0 | none |
| `field_art.banks` (8) | 224 | 224 | 0 | 0 | none |
| everything else, **now that `MODELS.BIG` has its own row** | 931 | 55 | 279 | **2** | 3 of 3 |
| **all 211 archives** (`textures.bank_inventory`) | **58,604** | **23,954** | **30,304** | **1,008** | 3 of 3 |

The zeros are the honest part. **Every image on the uniform-preview, face and
field-art pages is `0x0E`**, so nothing there can be paired even though two kits
and a portrait are on screen in these very frames — §5 is why. The kit row above
them is where those two on-screen kits actually are: 167 of its images are
confirmed, and the parts they fall on are `lace` (155), `hat` (4), `llod` (3),
`bglb` and `bglt` (2 each) and `hlm1` (1) — the low-detail equipment a wide
camera draws [M]. And 1,008 confirmed of
58,604 is a fact about a three-frame capture, not about the disc:
`replacement_identity` answers with the confirmed name where there is one, the
derived name where there is not, and the page says which of the two it is
giving you.

**Does the deriver agree with the emulator?** For every confirmed filename, the
lane's derived names were compared with it string for string [M]:

| GS pixel mode | confirmed names | derived name is the confirmed name | a different name | no name derived |
|---|---:|---:|---:|---:|
| `PSMT8` (19) | 2,088 | 1,890 | 0 | 198 |
| `PSMT8H` (27) | 1,035 | 1,035 | 0 | 0 |
| `PSMCT16` (2) | 60 | 0 | 0 | 60 |
| **total** | **3,183** | **2,925** | **0** | **258** |

**The `PSMT8H` row is a finding, and it is the reason the total is clean.**
Those 1,035 names are of textures the game uploads as a *high-byte* surface —
the 8-bit index in the top byte of a 32-bit word — and until this run the
deriver only ever produced the `PSMT8` reading, so **every one of them was a
disagreement**: a different `bits` word *and* a different TEX0 hash for the same
pixels. Measured against the dump, the GS-block reading reproduces none of the
1,035 and the plain **linear** reading reproduces all of them, which is what
`pcsx2_texture_name.hashed_stream` now does for PSM 27; `derive_names` offers
both modes because nothing on the disc says which one a draw will use.

**The 258 with no derived name are 33 images, and the missing half is the
CLUT** [M]. They are small widgets — 29 of the 33 are 8x8 — carrying a palette
of 1, 2 or 9 entries, and this module derives a name only for an 8-bit image
with a 256-entry palette, because PCSX2 hashes a 256-entry CLUT and the padding
is not on the disc. It is not: the same 8x8 widget is dumped under several
different CLUT hashes across three frames, so the game builds those CLUTs at
run time and recolours them. The *TEX0* half is ours, though — of the 172
distinct filenames involved, **132 have a TEX0 hash the disc bytes reproduce
exactly, and every one of those 132 is a `PSMT8` name**; the 40 that do not are
`PSMCT16` (PSM 2) draws, where the game uploaded the widget as 16-bit direct
colour and the emulator hashed something else. So for these the dump is the
only thing that can name them, and the page says exactly that rather than
offering a name it cannot build.

The evidence is `docs/product/measured/mvp05_ps2/pcsx2-texture-identities.json`
(the table the lane reads), `…/pcsx2-texture-identity-derivation.json` (the
census above) and `…/shps-0x0e-dump-pairing.json` (§5). **Naming a texture is
not loading a pack**: no pack built from these names has been loaded in an
emulator, so no lane offers a *Write PCSX2 pack* step.

---

## 5. `SHPS` code `0x0E`: the verdict

Every uniform *preview* swatch, portrait, head texture, loading screen and
piece of field art on the disc is code `0x0E` — and so is the high-detail half
of every worn kit, though not the rest of it (§9). The bounded hour the brief allowed established what
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
back nothing rather than a half-right picture. The Uniforms page is the
exception, and §9 is why: most of what a player wears was never `0x0E`. Whoever picks it up starts at
the selector semantics with the block map, the endpoint order and the raster
order settled.

### 5.1 The answer key that is not in the dump [M]

The bounded hour ended on inference from the encoded bytes. The way to end the
argument instead is an **answer key** — a picture of what one of these images
decodes to — and a PCSX2 texture dump is one, because the emulator writes out
the decoded texels of whatever the game drew. The three frames of §4.2 were
searched for one, by seven tests — two through the palette, which turn out to
prove nothing here, and five that do not need it. **There is none in them:**

| # | test | candidates |
|---|---|---:|
| 1 | the dumped filename's CLUT hash equals a `0x0E` image's palette | 1 picture |
| 2 | every colour a dumped picture uses is in a `0x0E` image's palette, in any order | the same 1 |
| 3 | the payload can hold the picture (`w*h*3/8` bytes against the dumped texels' compressed size) | **0** |
| 4 | the true index image has ≤ 4 distinct indices in *some* 16-texel block shape | **0** |
| 5 | the picture correlates with a `0x0E` image's endpoint thumbnail, above the null | **0** |
| 6 | that candidate's pixels lie between its block's two endpoint colours | **0** |
| 7 | **no** 8-bit texture the game hands the GS, from a dump with no source filter, exceeds four indices in a 4x4 block (§5.2) | **0** |

Test 2 is the one with recall — this game does re-order some CLUTs before
uploading them — and it is calibrated: on **198 pairings already known to be
right whose CLUT hash differs from the disc palette, the colour-set test holds
198 of 198** [M]. Across all 23,954 `0x0E` images and all 436 distinct dumped
textures it finds one pairing, and 939 of the 1,308 dumped files have a size
some `0x0E` image also has, so it was not starved of candidates.

The one candidate is a 128x128 `PSMT8` texture whose CLUT is byte for byte the
palette of one `MODELS.BIG` `0x0E` image — the only image on the disc carrying
that palette. Inverting the palette on it succeeds completely (0 of 16,384
pixels outside it, 528 ambiguous, 251 distinct indices), so the CLUT is
certainly that image's; the texels are certainly not its decode. They compress
to **122,072 bits** and the payload holds **49,152**, and their true index
image reaches **16** distinct indices in a block where two endpoints and 2-bit
selectors allow four — in every 16-texel shape tried (4x4, 8x2, 2x8, 16x1,
1x16).

**Tests 1 and 2 go through the palette and two real decoders would escape
them** — one that rebuilds the CLUT at upload, which this game does for its
small widgets, and one that interpolates in *colour* space between `pal[i0]`
and `pal[i1]` and never uses the palette as a codebook, which is what two
endpoint bytes rather than four RGB565 words buys. Tests 5 and 6 do not.
Test 5 pairs the two **pictures**: every `0x0E` image gets an *endpoint
thumbnail* — `(w/4) x (h/4)`, each block the midpoint of its two endpoint
colours, which for a portrait bank renders as unmistakable faces — every dumped
picture gets its 4x4-block means, and the two are cross-correlated, both sides
filtered on contrast because flat thumbnails correlate with each other. It is
read against a **null**: the dumped pictures that already pair to a `0x02`
image cannot be `0x0E`, so what they score is what an unrelated pair scores.
47 probe pictures against 11,618 contrast-carrying `0x0E` thumbnails [M]:

| population | pictures | median | best |
|---|---:|---:|---:|
| null — already paired, so **cannot** be `0x0E` | 28 | 0.421 | **0.842** |
| everything else | 19 | 0.265 | 0.943 |

The candidates score *below* the null. One clears its ceiling, and test 6
disposes of it: under a two-endpoint codec every pixel sits on the segment
between its block's endpoint colours, so the residual is quantisation — and the
measured residual is **25.5 of 255 with 5.3% of pixels within 8**, barely
better than snapping to the endpoints alone (26.1), where a real interpolating
codec improves sharply.

**What that says is where the decode is not.** MVP's `0x0E` art does not reach
the GS as an indexed texture PCSX2's dumper writes out, and not as a
direct-colour one either, even though these frames drew some: one is a batter
introduction card with a portrait on it and every portrait on the disc is
`0x0E`, and both batters are in kits and every kit is `0x0E`. **Another scene
will not help.** The whole search is
`docs/product/measured/mvp05_ps2/shps-0x0e-dump-pairing.json`. The endpoint
word order and the block-raster map are re-confirmed by the thumbnails across
all 23,831 `0x0E` images with a 256-entry palette; the selector semantics are
untouched.

### 5.2 The dumper's filter came off, and the answer did not change [M]

All of §5.1 rests on a *replacement* texture dump, and that dumper writes only
a texture whose source is a plain transfer — so a texture the game builds on
the GS never appears in it. The same three frames were replayed through the
**per-draw** dumper, which writes every texture a draw uses whatever its
source, every render target and every EE-to-GS upload. A `P_8` upload's PNG
carries the uploaded byte in its red channel, so it **is** the index image and
no palette has to be identified to read it:

| | |
|---|---:|
| distinct 8-bit textures the game hands the GS | 135 |
| **byte-identical to a `0x02` image on the disc** | 117 |
| with no disc twin | 18 |
| of those, any that could be a two-endpoint block decode | **0** |
| distinct CLUTs uploaded, and how many a `0x0E` image owns | 44 / **44** |
| the same, for a `0x02` image | **0** |
| disc `0x02` images the uploads identify byte-exactly | 2,874 |

**The CLUT test was never evidence about `0x0E`.** Every CLUT these frames
upload is a `0x0E` image's palette and none is a `0x02` image's, while nearly
every texture drawn with them is a `0x02` image — so an `0x0E` block's palette
is the CLUT its **bank** draws with, shared across the bank. The single "hit"
§5.1 reports is that and nothing more.

**Nothing the game draws is a block decode.** Of the 18 uploads with no disc
twin, every one runs to 12–16 distinct indices in a 4x4 block where two
endpoints and 2-bit selectors allow four.

**And the reason is the LOD.** The kit on the batter is `MODELS.BIG:990:0`,
matched byte for byte; its bank tags it **`llod`**, and the same bank's `0x0E`
images are the high-detail parts (`jers`, `jerk`, `msk1`, `slvl`, `slvr`,
`lega`, `shoe`). These frames draw the low LOD. **An on-screen kit is
therefore an editable `0x02` image in `MODELS.BIG`, not one of the `0x0E`
images the uniforms page lists** — and `MODELS.BIG` was on no writer page when
that was written. **§9 is the census that followed and the writer it earned.**

**The capture to ask for is a close-up** [A] — a replay or cutscene camera on a
player, or a portrait at full size — where the game has a reason to load the
high-detail LOD. A savestate would serve too, since EE RAM holds the decoded
buffer whenever one is built. Neither is in the fixtures.

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
3a. **The kit.** Diagonal bands in `u010a.ssh`'s `llod` and `hat`, which a
   wide camera on that club should draw, and in `f010a.ssh`'s `A___`, which
   should appear in that club's nameplates. If the kit changes and the letter
   does not, the game composites nameplates from somewhere else and §9's
   reading of the lettering banks is wrong.
4. **The audio.** A two-second tone where a crowd bed was.
5. **The negative that matters.** The game must still *load*. A rewritten
   size word in an archive's table is the step most likely to be checked.

Until those are recorded every writer row stays `offline-writer-proved` and
every receipt keeps the sentence that says so.

**Also unproved, and not on the boot list:** whether PCSX2 *loads* a pack built
from these names. 1,008 of them are now confirmed against a dump (§4.2), which
means the emulator wrote those filenames while drawing those pixels; it does
not mean a pack under them has been put back in and seen on screen. That is a
separate trial and nobody has run it.

---

## 7. Verifying this document

```bash
export QT_QPA_PLATFORM=offscreen
python -m mod_editor.games conformance --game mvp05_ps2          # 493 of 493
python tools/validate_game_lane.py --game mvp05_ps2 --all         # five PASS tokens
PYTHONPATH=. python tests/mod_editor/test_mvp05_ps2_lanes.py
PYTHONPATH=. python tests/mod_editor/test_mvp05_ps2_identities.py
PYTHONPATH=. python tests/mod_editor/test_ea_big.py tests/mod_editor/test_ea_shps.py
PYTHONPATH=. python tests/mod_editor/test_pcsx2_texture_name.py
python tools/mvp05_ps2_texture_identities.py --selftest
```

The disc numbers are reproduced by `python -m mod_editor.games.mvp05_ps2.<lane> --source <iso>`
for each lane module; each prints one line of counts and writes the
catalogue document with `--out`. §4.2's three tables are rebuilt in one command
from the disc and a dump directory — about three minutes, of which the disc
walk is 188 seconds and everything after it is seconds:

```bash
python tools/mvp05_ps2_texture_identities.py \
    --source <iso> --dump-dir <texdumps>/SLUS-21135 \
    --write-index <scratch>/index.jsonl --frame-labels <scratch>/frames.json
```

`--index <scratch>/index.jsonl` on a later run reads that index instead of
walking the disc again; the index carries the palette-join hits too, so the
`0x0E` verdict is reproduced from it without a second walk.

§9's tables are rebuilt in one command — about eleven minutes, of which four
are the archive walk and seven are re-packing all 1,407 banks:

```bash
python -m mod_editor.games.mvp05_ps2.art_lane --lane kits --source <iso> \
    --parts docs/product/measured/mvp05_ps2/models-big-parts.json --slot-fit
```

Drop `--slot-fit` for the per-part table alone.

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

---

## 9. `MODELS.BIG`: the census, and the writer it earned [M]

§5.2 ended on a gap: the kit on a batter is an editable `0x02` image and
`MODELS.BIG` was on no writer page. This section is the measurement that
closed it. Everything here is in
`docs/product/measured/mvp05_ps2/models-big-parts.json`, rebuilt by the command
in §7.

### 9.1 Three bank families, told apart by name and confirmed by their tags

`MODELS.BIG` holds **1,407 `SHPS` banks beside 549 `.ord`/`.orl` model pairs**,
in 2,505 entries. Every bank's name puts it in one of three families, and every
family has one tag set:

| family | names | banks | images | `0x02` | `0x0E` | `0x05` | tags per bank |
|---|---|---:|---:|---:|---:|---:|---:|
| kit | `u<nnn><v>.ssh`, plus `umpire`, `umpirec`, `uniform` | 436 | 13,921 | **5,657** | 8,252 | 12 | 32 |
| lettering | `f<nnn><v>.ssh`, `a<nnn><v>.ssh`, `teamfont` | 467 | 16,110 | **16,110** | 0 | 0 | 36 (10 for `a<nnn><v>`) |
| head | `c<nnn>.ssh` | 504 | 504 | 0 | 504 | 0 | 1 |
| **all** | | **1,407** | **30,535** | **21,767** | **8,756** | **12** | |

The families are not read off the names alone — the name predicts the tag set
and the tag set confirms it, with no counter-example in 1,407 banks. A name
this rule does not recognise is reported as `other`, never guessed.

**Which bank is which club, and which is nobody's.** `DATABASE.BIG!team.dat`
column 6, `team_artid`, runs 1..126 across the table's 126 rows, and the `u`
and `f` families each carry exactly the bank numbers 0..125: **`team_artid` − 1
is the bank number, and the map is a bijection** [M]. So a bank names its club
by rule, and this repository carries the rule rather than a table of club names,
which would be disc payload. `<v>` is the uniform variant, `a`..`p`: 32 of the
126 clubs (the two top leagues) carry 6 to 12 variants each and the rest carry
1 or 2 [M]. **The four named banks belong to no club** — `umpire` and `umpirec`
are officials' kits, `uniform` a create-a-team base, `teamfont` a shared
lowercase-and-digits sheet — which is why the page names banks and lets the rule
name clubs, instead of claiming a team attribution per row.

**What `UNIFORMS.BIG` is, then.** Its 555 banks are 128x128 `0x0E` images with
431 one-pixel `0x01` stubs beside them, keyed by the same `<nnn><v>` scheme: the
uniform *preview* swatches. That they are the select-screen art is read from
their name, shape and key, not witnessed — no frame of the three-frame dump
reached that screen, and the row says so.

### 9.2 The part table: what is writable, and what is not

One row per four-character part tag of the 436 kit banks. **The dichotomy is
total**: a tag is `0x02` in every bank or `0x0E` in every bank, never mixed.
The `0x05` column is a handful of 8x8 direct-colour stubs standing in where a
part is unused. `confirmed` is how many of that part the three-frame PCSX2 dump
names by exact pixel equality (§4.2).

| tag | images | `0x02` | `0x0E` | `0x05` | confirmed | sizes |
|---|---:|---:|---:|---:|---:|---|
| `aslv` | 436 | 436 | 0 | 0 | 0 | 64x64 ×434, 8x8 ×2 |
| `hat` | 436 | 436 | 0 | 0 | 4 | 128x64 |
| `hlm1` | 436 | 436 | 0 | 0 | 1 | 128x64 ×434, 64x64 ×2 |
| `lace` | 436 | 436 | 0 | 0 | 155 | 32x32 |
| `msk2` | 436 | 436 | 0 | 0 | 0 | 8x8 ×435, 64x64 ×1 |
| `msk3` | 436 | 436 | 0 | 0 | 0 | 64x32 ×433, 128x32 ×3 |
| `bglb` | 435 | 435 | 0 | 0 | 2 | 64x64 ×433, 8x8 ×2 |
| `bglt` | 435 | 435 | 0 | 0 | 2 | 64x64 ×433, 8x8 ×2 |
| `hhlm` | 435 | 435 | 0 | 0 | 0 | 128x128 ×433, 8x8 ×2 |
| `llod` | 435 | 435 | 0 | 0 | 3 | 128x128 |
| `wrbn` | 435 | 435 | 0 | 0 | 0 | 32x32 ×433, 8x8 ×2 |
| `merk` | 433 | 433 | 0 | 0 | 0 | 64x64 |
| `mslv` | 433 | 433 | 0 | 0 | 0 | 64x128 |
| `chst` | 435 | 0 | 433 | 2 | 0 | 128x128 ×433, 8x8 ×2 |
| `jerf` | 435 | 0 | 433 | 2 | 0 | 128x128 ×433, 8x8 ×2 |
| `jerk` | 436 | 0 | 436 | 0 | 0 | 128x128 |
| `jers` | 436 | 0 | 436 | 0 | 0 | 128x128 |
| `jert` | 435 | 0 | 433 | 2 | 0 | 128x128 ×433, 8x8 ×2 |
| `jrfl` | 433 | 0 | 433 | 0 | 0 | 128x128 |
| `jrkl` | 434 | 0 | 434 | 0 | 0 | 128x128 |
| `jrsl` | 436 | 0 | 436 | 0 | 0 | 128x128 |
| `jrtl` | 433 | 0 | 433 | 0 | 0 | 128x128 |
| `lega` | 436 | 0 | 436 | 0 | 0 | 128x256 ×435, 128x128 ×1 |
| `legb` | 435 | 0 | 433 | 2 | 0 | 128x256 ×433, 8x8 ×2 |
| `legc` | 435 | 0 | 433 | 2 | 0 | 128x256 ×433, 8x8 ×2 |
| `legd` | 433 | 0 | 433 | 0 | 0 | 128x256 |
| `merf` | 433 | 0 | 433 | 0 | 0 | 128x128 |
| `msk1` | 436 | 0 | 436 | 0 | 0 | 128x128 |
| `shn1` | 435 | 0 | 433 | 2 | 0 | 128x128 ×433, 8x8 ×2 |
| `shoe` | 436 | 0 | 436 | 0 | 0 | 128x64 ×433, 64x32 ×3 |
| `slvl` | 436 | 0 | 436 | 0 | 0 | 128x64 |
| `slvr` | 436 | 0 | 436 | 0 | 0 | 128x64 |

**Writable: 13 tags, 5,657 images.** `llod` is the whole kit at low detail and
is the texture §5.2 caught the game drawing; `hat`, `hlm1` and `hhlm` are caps
and helmets; `aslv` and `mslv` sleeves; `bglb`/`bglt` batting gloves; `wrbn` a
wristband; `lace`, `merk`, `msk2`, `msk3` the small equipment.

**Refused: 19 tags, 8,252 images.** `jers`/`jerk`/`jrsl`/`jrkl`/`jerf`/`jert`/
`jrfl`/`jrtl`/`merf` are the high-detail jersey in its variants; `lega`..`legd`
the trousers; `msk1`, `shoe`, `slvl`, `slvr`, `chst`, `shn1` the rest. All
`0x0E`, all §5.

**The lettering banks are 62 tags and every one is writable**: `A___`..`Z___`
(438 each, 16x32), `a___`..`z___` (2 each, 16x32) and `zig0`..`zig9` (467 each,
mostly 32x64) — 16,110 images. These are the glyphs the game composites into a
nameplate and a squad number, which is what §4.2's unmatched pile said it was
doing ("nameplates and numbers the game composites at run time"). **That reading
is inference from the tag names and the per-club keying; no frame of the dump
drew one**, so the boot list in §6 asks for it directly.

**The 504 head banks are one `0x0E` `face` image each**, 128x256. They are
listed by this lane because they are in this archive; nothing draws them.

### 9.3 The writer's real bound is the slot, and it is thin

The bank goes back inside the slot its entry already owns. Re-packing all 1,407
banks with our own RefPack encoder, **unedited**:

| family | banks | re-pack inside the slot | over it |
|---|---:|---:|---:|
| kit | 436 | 416 | 20 |
| lettering | 467 | 461 | 6 |
| head | 504 | 504 | 0 |
| **all** | **1,407** | **1,381** (98.2 per cent) | **26** |

Headroom runs from **-89 to +388 bytes, median 39** [M]. That is a far tighter
margin than the CSV tables enjoy, and it is why the refusal matters: an edit
that compresses *worse* than the pixels it replaced can push a bank that fits
here over the line, and `ea_big.rewrite_entry` refuses it naming the byte count
rather than moving an entry. The trial in §4 chose two banks with headroom on
purpose, and says so.

### 9.4 What a modder can and cannot change, plainly

- **Can:** the low-detail whole kit, the cap, the helmet (both), the sleeves,
  the batting gloves, the wristband, the laces and the small equipment masks,
  for any of 436 kit banks; and every letter and digit of the nameplate and
  number sheets, for any of 467 lettering banks. 21,767 images.
- **Cannot:** the high-detail jersey, the trousers, the shoes, the arm sleeves
  and the chest and shin pieces — 8,252 images, all `SHPS` code `0x0E`, whose
  per-pixel selectors are undecoded (§5). Nor the 504 head textures, nor the
  986 preview swatches on the row beside it.
- **Cannot, on 26 banks:** whatever re-packs larger than its slot. The refusal
  names the byte count; nothing repacks the archive.
- **Not proved anywhere:** that the game loads any of it. **No rebuilt image
  has been booted** (§6), and no PCSX2 replacement pack built from these names
  has been loaded either (§4.2). The 167 confirmed names say the emulator wrote
  those filenames while drawing those pixels; they do not say a pack under them
  comes back.

So MVP has a uniform writer, and it reaches most of the kit and all of the
lettering. It is not a complete uniform editor and the page does not say it is:
the shirt and trousers a close camera shows are the `0x0E` half, and decoding
those selectors is the one piece of work that would finish it — the same piece
that would finish the portraits and the field art (§5).
