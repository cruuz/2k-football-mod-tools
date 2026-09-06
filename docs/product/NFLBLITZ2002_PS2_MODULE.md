# NFL Blitz 2002 (PlayStation 2) — the module

**What this document is.** `mod_editor/games/nflblitz2002_ps2/` is the fifth game
on the Game Studio shell and the first Midway title: no EA `TERF`, no `BIG`, no
`TDB`, and no Visual Concepts pack. The whole game is **one ZIP whose every
member is stored**, with Midway's pre-built index beside it. Nothing in this
toolchain's EA stack carries over; both readers are new. The owner's scoping
study `docs/owner/scoping/BLITZ_AND1_FORMATS.md` is what this was built from;
where the two differ, this document is current and says so.

**Evidence tags.** **[M]** measured on the retail SLUS-20051 disc this box
holds, read-only; **[S]** sourced; **[A]** assumed.

**Retail-free.** Counts, names, offsets, lengths and digests. No line, name,
pixel, palette entry or record from the disc is in this repository.

---

## 1. The verdict, in six sentences

1. **All fourteen pages are answered**: four writers at
   `offline-writer-proved`, two export lanes at `extract-only`, two inventories
   at `read-only-mapped`, and one page note each for the five pages the disc
   gives nothing to write (§3).
2. **The ZIP pair is measured exhaustively, not sampled.** All 2,426 index
   entries match the archive on names, sizes and data offsets; all 2,426 CRC-32
   columns agree; 600 of 600 recomputed CRC-32s over the stored bytes agree; all
   2,426 members are stored and every local header's extra field is empty [M].
3. **A stored member can be replaced where it lies, and its CRC-32 lives in
   three places.** The local file header, the central directory and the `.ZIH`
   index. `blitz_zip.plan_member_replacement` returns all three or refuses;
   there is no path through the module that writes one without the others.
4. **Four probes ran and all four returned something** (§5): `roster.rst`
   yielded a writer, `CPTH` yielded a reader, `WIFF` yielded a head-level
   identity, and the `.dff` question is answered — the ids **are** RenderWare
   and the map's length rule was simply the wrong rule for a multi-section file.
5. **The GS un-swizzle was measured, not assumed** (§4). The 8-bit answer beats
   reading the bytes linearly by 232% and is taken; no 4-bit candidate separates
   from the null, so 6,231 rasters are listed and not drawn with that number as
   the reason.
6. **Every writer is proved twice offline** — on the synthetic disc in CI and on
   the retail disc by hand, chained so the last image carries every edit (§6) —
   and **no rebuilt image has been booted**; every receipt says so.

## 2. What the module is made of

| file | what it holds |
|---|---|
| `containers.py` | the identity digests, which member feeds which page, the ZIP pair opened in place off the image, the text line-slot and roster readers, and every synthetic builder |
| `disc_identity.py` | the shared PS2 identifier, given this game's identity |
| `zip_lane.py` | the one way anything is written: same-length members, three CRC sites, the shared ISO9660 writer in, its independent verifier out |
| `text_lane.py` | `TextLineLane`, three rows: the crowd tables, `field.tab`, the trivia banks |
| `roster_lane.py` | `RosterNameLane`, one row: either 32-byte name field of any of the 738 records |
| `texture_lane.py` | `TextureDictionaryLane`, three rows: the all-textures inventory and two export lanes |
| `camera_lane.py` | `ContainerInventoryLane`, one row: camera paths, `WIFF` containers, RenderWare clumps |
| `validators.json`, `tools/validate_nflblitz2002_ps2_*.{sh,bat}` | five validators through `tools/validate_game_lane.py` |
| `tests/mod_editor/test_nflblitz2002_ps2_lanes.py`, `..._module.py` | 24 tests on the synthetic disc, plus the conformance harness |

Shared code this module added: `mod_editor/games/_formats/blitz_zip.py` (the
Midway stored ZIP, both `.ZIH` shapes, and the bounded three-place writer) and
`mod_editor/games/_formats/rw_txd.py` (RenderWare texture dictionaries with PS2
native rasters). Both joined the release allowlist and the runtime closure.
17 tests prove `blitz_zip` and 14 prove `rw_txd`, each on sources they build.

## 3. The fourteen pages

| page | lane (row) | classification | what it writes, or why not |
|---|---|---|---|
| Uniforms & Equipment | `uniforms.team_textures` | `extract-only` | exports any 8-bit or 32-bit raster of the 594 team-prefixed dictionaries as PNG, with a derived PCSX2 name: 2,408 of 8,434 rasters decode; the other 6,026 are 4-bit and listed, §4 |
| Names, Numbers & Faces | `rosters.player_names` | `offline-writer-proved` | either 32-byte name field of any of the 738 records of `roster.rst` |
| Text & Team Identity | `identity.crowd_tables` | `offline-writer-proved` | any line of the 31 `*_crowd.ini` tables, inside its own span |
| Field Art & Create-Team Art | — | page note | the disc's field is `field.tab`, edited on Gameplay; every other art member is a texture dictionary |
| Stadiums | — | page note | stadium geometry is in the 1,272 `.dff` clumps; reading a clump is a different reader (§5) |
| Presentation | `presentation.camera_paths` | `read-only-mapped` | lists 85 camera paths, 190 `WIFF` containers and 1,272 clumps; a camera record's fields are not measured |
| Menus & UI | `menus.screen_textures` | `extract-only` | exports any 8-bit or 32-bit raster of the other 167 dictionaries: 1,781 of 1,986 rasters decode |
| The Crib | — | page note | not an NFL Blitz concept |
| Audio | — | page note | all of it is one 137,538,180-byte `mslasset.ms2`, a Midway sound bank another module owns |
| Gameplay | `gameplay.field_table` | `offline-writer-proved` | any line of `field.tab`, inside its own span |
| Playbooks & Plays | `playbooks.trivia_banks` | `offline-writer-proved` | any of the 40-byte trivia records |
| All Textures | `textures.dictionary_inventory` | `read-only-mapped` | every dictionary and every raster on the disc, one row per dictionary |
| Saves | — | page note | a save is not the disc; the two `.ico` members are dashboard icons |
| Build & Share | — | the shell's own | — |

Every page note is one sentence in `game.json`, and every one states a
measurement rather than a plan.

**The boot executable, for the record** [M]: `SLUS_200.51`, 2,342,232 bytes,
sha256 `d165b3c8…b60fe85d`, PCSX2 CRC `3A32FD60`. No patch site on it has been
located by this project, so the Gameplay page carries the `field.tab` writer and
no code patcher.

### 3.1 The text writers (three rows, one class)

72 members are plain text, in two shapes [M]: the 31 `*_crowd.ini` tables,
`field.tab` and (on the 2003 disc) `credits.txt` are printable ASCII with CRLF
endings, 32 of 32; the 40 `.trv` trivia banks are `size % 40 == 0` on 40 of 40
with every record printable ASCII padded with NUL.

A line owns its own bytes. A replacement must fit that span and is padded to it —
NUL in a trivia record, spaces in a CRLF line — so the member's length never
changes, which is what lets it go back into a stored ZIP where it lies.
`check_edit` refuses a value too long (naming the byte count), a line break, a
NUL, and text outside Latin-1.

### 3.2 The roster writer

`roster.rst` is 41 blocks of `u32 18` + 18 × 100-byte records, which is its
73,964 bytes exactly [M]. §5 has the identities. A name field is 32 bytes of
NUL-terminated ASCII padded with `0xCD` — uninitialised MSVC heap fill, which is
what tells you it is a fixed struct member and not a string table. A replacement
fits or is refused, so the member's length never changes.

The 36 numeric bytes are **listed and not written**. Two columns have exact
identities — byte +68 is the block ordinal, byte +72 takes exactly 18 distinct
values 0..17 — and fourteen more sit in a 0..100 range that looks like ratings.
Looking like ratings is not being ratings, so the lane publishes a column census
for all 36 and offers an editor for none of them.

The verifier does one thing more than the shared one: it re-parses the rewritten
roster and requires every record to still carry its block's ordinal at byte +68.

### 3.3 The art (two exports, one inventory, one walker)

One walker parses every dictionary of a selection and lists every raster with
its size, depth, raster format, GS pixel mode and section sizes. A dictionary
belongs to a team when its name is `<a team prefix>_...`, and the prefixes are
read off the disc's own `*_crowd.ini` members rather than listed in the module:
594 of the 761 dictionaries carry one [M]. An export lane
adds `decode_png` and `replacement_identity`; `encode` refuses by name. The
inventory lane is the same walker over every dictionary on the disc, read-only.

**Identities are derived, none confirmed.** A name is what PCSX2's documented
rules compute from the raster's own bytes, through the shared
`pcsx2_texture_name` whose GS block layout is measured against 33 dumps *of a
different game*. No texture dump of either Blitz disc exists in this project.

## 4. The GS layout, measured [M]

The data section of a PS2 raster is a GIF chain: an A+D packet setting
`TRXPOS` / `TRXREG` / `TRXDIR`, then an `IMAGE`-mode tag whose payload is the GS
upload. The upload is **not** the texture's linear pixels: an 8-bit texture is
transferred as `PSMCT32` at half its width and half its height, a 4-bit one as
`PSMCT16` at the same halved size, so the disc bytes are the GS's own memory
image.

Which un-swizzle is right was decided by measurement, on 30 rasters of the
retail disc, scoring each candidate by the mean absolute difference between
horizontally adjacent decoded RGB values — real art is locally coherent and a
wrong layout destroys that. Lower is better:

| depth | layout | score |
|---|---|---:|
| 8-bit | **PSMCT32 composition** | **7.32** |
| 8-bit | GS block image, inverted | 15.93 |
| 8-bit | raw linear (the null) | 24.26 |
| 4-bit | half-width via the 8-bit routine | 18.75 |
| 4-bit | the published 4-bit routine | 20.14 |
| 4-bit | raw linear (the null) | 20.53 |
| 4-bit | GS block image, inverted | 28.16 |

The 8-bit answer beats the null by 232% and is taken. **No 4-bit candidate
separates from the null** — the best beats it by 9% — so `decode_rgba` refuses a
4-bit raster by name and the refusal quotes those two numbers. Guessing there
would put a wrong picture on a page. 32-bit rasters are direct colour and need
no index step.

Per disc: 4,189 of 10,420 rasters decode (2002) and 6,392 of 11,828 (2003);
4,166 and 6,365 identities are derived; 0 refusals in either walk [M].
`docs/product/measured/nflblitz2002_ps2/texture-dictionaries.json` carries the
counts and the scores.

## 5. The four probes [M]

`docs/product/measured/nflblitz2002_ps2/probes.json` carries all of this
verbatim; each probe either became a reader with a page or a page note with a
measured reason.

**`roster.rst` — yielded.** 41 blocks (2002) / 42 (2003) of 1,804 bytes, which
is the member exactly on both discs; every block's header word is 18 (41 of 41,
42 of 42); every record's two 32-byte name fields are NUL-terminated ASCII (738
of 738, 756 of 756); every record's byte +68 equals its block's ordinal (738 of
738, 756 of 756). **The cross-check the brief asked for holds**: the disc carries
one `<two letters>_crowd.ini` and one `<two letters>_glogo.rtd` per NFL team — 31
of each on the 2002 disc, 32 on the 2003 disc — and the prefix the 2003 disc adds
to *both* lists is `ht`, the Houston Texans, the team the NFL added for the 2002
season. The roster's block count moves with them, 41 to 42, leaving a constant
ten blocks the team lists do not name. **Which** block is which team is not
measured and is not claimed.

**`CPTH` (the study's `HTPC`) — yielded, and a correction.** The scoping study
names this family `HTPC`, which is its tag read as a little-endian *word*; the
bytes on the disc are `CPTH` — camera path. `16 + records * 32 == the member` on
85 of 85 and 88 of 88 [M]. Header word 1 takes four values (7, 1, 5, 3) and is
reported unnamed. A record's 32 bytes read as IEEE floats and nothing here says
which is a position and which a time, so the lane lists and offers no editor.

**`WIFF` — yielded at the head.** It is a **big-endian RIFF**: the `u32` after
the tag plus 8 is the member's own length on 190 of 190 and 209 of 209 [M], and
the form type is `WIPS` (167 / 181), `WOMS` (16 / 21) or `WOM ` (7 / 7). No
chunk inside one is read.

**`.dff` — answered.** The map left all 2,708 as a raw magic because
`section bytes + 12 == the file` fails on every one. It fails because **a DFF
stream is more than one top-level section**: a walk over the whole member
consumes it exactly on 1,043 of 1,272 and 1,167 of 1,436, and the sequence is
`Clump(0x10)` then `Extension(0x03)` on 1,043 and 1,145, or `Clump` alone on 162
and 149 [M]. Library version words are `0x0401ffff` (680 / 843) and `0x00000310`
(592 / 593) — both RenderWare 3.x. So the id is not a coincidence and Midway
wrote no variant; the map's rule was the wrong rule for a multi-section file.
Reading a clump's geometry is a different reader and is not done here.

## 6. The real-disc trial [M]

Read-only source, scratch destinations, chained so each image carries every edit
before it, each verified against its own source, every image deleted afterwards.
Every edit is a value this project chose — a fixture line, a fixture name — so
any byte difference would be the writer's.

| step | lane | what was written | declared ranges / bytes | verdict |
|---|---|---|---:|---|
| 1 | `identity.crowd_tables` | a crowd-table line, inside its own span | 4 / 361,524,828 | PASS |
| 2 | `gameplay.field_table` | a `field.tab` line, inside its own span | 4 / 361,524,828 | PASS |
| 3 | `playbooks.trivia_banks` | a 40-byte trivia record | 4 / 361,524,828 | PASS |
| 4 | `rosters.player_names` | both name fields of one record | 4 / 361,524,828 | PASS |

Every destination is 1,464,205,312 bytes, the length of the source. The declared
bytes are the ISO writer's own accounting — the whole extent of each rewritten
file plus its directory record — which is a superset of the handful of bytes the
member writer changed; the receipt names the member, its offset, its length, its
old CRC-32 and its new one.

The independent verifier ran on each step, importing none of the patcher: it
re-derived the archive and the index from the destination's own bytes, required
all 2,426 members present at their original offsets and lengths, required every
member the receipt did not name **byte-identical by streaming digest** —
including the 137 MB sound bank, which is exactly where an undeclared change
would hide — required the replaced member's bytes to recompute to the CRC-32 the
local header, the central directory and the index now all carry, and handed the
image-level claim to `tools/ps2_iso9660_verify.py`'s own ISO9660 decoder.
`docs/product/measured/nflblitz2002_ps2/writer-trial.json` carries the run.

**No rebuilt image has been booted** in an emulator or on hardware. The game's
acceptance of a rewritten member is not claimed anywhere.

## 7. What a second Blitz disc costs

`docs/product/NFLBLITZ2003_PS2_MODULE.md`. In short: the archive's name, the
index's record shape, and the counts. Nothing else (§2 there has the numbers).

## 8. What is not done

* **No texture writer.** Re-swizzling an 8-bit raster into the GS memory image
  and rewriting the member at its own length is within these readers —
  `rw_txd._swizzle8` is the exact inverse the synthetic builder already uses —
  and it is **not proved**, so it is not offered.
* **No 4-bit decode** (§4), which is 6,231 rasters on the 2002 disc.
* **No `WIFF` chunk reader, no `.dff` geometry reader, no camera-record
  decode**, each with its measured reason in §5.
* **`RYWM` (36 / 37 `.rsc` members) and `EKAB` (4 / 5 `.ban` members)** were not
  probed: they are outside the four the brief named. `EKAB`'s `word1 + 8 == the
  member` holds on 4 of 4 and 5 of 5 [M], which is the only thing read.
* **`mslasset.ms2`** is another module's format and was not opened.
* **Nothing is runtime-proved.** No image built here has been booted.
