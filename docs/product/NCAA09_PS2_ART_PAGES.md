# NCAA Football 09 (PlayStation 2) — the six art rows

Six of this module's fourteen rows are the same lane pointed at different
containers: `mod_editor/games/_lanes/terf_art.py`, which Madden NFL 09's five
art rows also instantiate. **Eleven rows, one lane, two discs.** This document
is what each of the six points at, what it will not touch, and what a write
costs there.

**Evidence tags.** **[M]** measured on the retail `SLUS-21752` disc;
**[S]** sourced; **[A]** assumed.

**Retail-free.** Names, offsets, lengths, counts and digests. No decoded pixel
is here or in the code.

---

## 1. The six rows

| row | page | containers | rung |
|---|---|---|---|
| `uniforms.texture_census` | Uniforms & Equipment | `UNIFORM`, `PLADATA`, `UIS_GEAR` | `extract-only` |
| `uniforms.disc_art_writer` | Uniforms & Equipment | the same three | `offline-writer-proved` |
| `rosters.face_textures` | Names, Numbers & Faces | `PLYRFACE`, `COACFACE` | `offline-writer-proved` |
| `stadiums.textures` | Stadiums | `STADATA`, `UIS_STAD` | `offline-writer-proved` |
| `field_art.textures` | Field Art & Create-Team Art | `FLDDATA`, `UIS_TMLO` | `offline-writer-proved` |
| `presentation.ui_textures` | Presentation | `FANDATA`, `MSCTDATA`, `LOADDATA` | `offline-writer-proved` |

The uniforms page carries two rows because its exporter earns a lower rung than
the writer beside it — the same shape Madden 09's uniforms page has. The other
four ship with both halves at once, and one lane already *is* both: the shell
draws preview, Export PNG and a checked Import PNG out of `decode_png` and
`encode`, and Build writes the edited texture into a NEW disc image.

---

## 2. What each container holds, and what a write costs there

The second half of that question is the preload caches, and it is not a
footnote: a `QL01` cache carries **byte copies** of container directories and of
individual members, and the game preloads from the copy. So a member rewrite is
free only while the container's first `data_offset` bytes stay put — and they
move the moment a member changes stored size or codec — and a member that is
itself copied has to be rewritten in the cache too, at a size no larger than the
slot it already occupies.

Measured on the retail disc [M]:

| container | members | formats | codec | cached directory | cached members |
|---|---:|---|---|---:|---:|
| `UNIFORM.DAT` | 1,206 | 1,200 `MMAP` | `LZH1` | ×4 | 3 |
| `PLADATA.DAT` | 889 | 888 `MMAP` | `LZH1` | ×1 | 8 |
| `UIS_GEAR.DAT` | 396 | 396 `MMAP` | stored | **none** | **none** |
| `PLYRFACE.DAT` | 80 | 64 `MMAP` | stored | ×2 | 54 |
| `COACFACE.DAT` | 18 | 18 `MMAP` | stored | ×2 | 4 |
| `STADATA.DAT` | 1,289 | 1,195 `MMAP`, 45 `SMF`, 4 `DMF` | mixed | ×2 | 45 |
| `UIS_STAD.DAT` | 245 | stored members | stored | ×1 | **none** |
| `FLDDATA.DAT` | 1,422 | 1,391 `LZH1` | `LZH1` | ×1 | 21 |
| `UIS_TMLO.DAT` | 399 | 399 `MMAP` | `LZH1` | ×1 | 8 |
| `FANDATA.DAT` | 257 | stored | stored | ×1 | **none** |
| `MSCTDATA.DAT` | 641 | 240 `MMAP`, 400 `DMF` | `LZH1` | ×1 | 12 |
| `LOADDATA.DAT` | 46 | 46 `MMAP`, 30 of them 854×480 | mixed | ×3 | 27 |

**`UIS_GEAR.DAT` is the cheapest target on the disc** and `UIS_STAD.DAT` and
`FANDATA.DAT` are next: a rewrite there disturbs a directory copy at most.
`PLYRFACE.DAT` is the other extreme and the most valuable to have proved, because
54 of its 80 members are carried in a cache — the path where a stale copy would
silently win.

---

## 3. What is not a texture is listed, not hidden

Every one of these containers carries members this lane cannot open, and every
one is counted by format per container rather than skipped [M]:

* **`SMF`** — EA static geometry (stadium shells, field meshes). 3,301 members
  disc-wide, 45 of them in `STADATA.DAT`.
* **`DMF`** — EA animated models (players, coaches, fans, mascots). 603 members,
  400 of them in `MSCTDATA.DAT`.
* **`MPCh`** — movie streams, 12 of them, all in `MOVIEDAT.DAT`.
* **`FNTS`** — 17 font sets in `FONTS.DAT` and `UIS_FONT.DAT`.

**No decoder for any of the four exists anywhere in this repository and no
layout for any of them is documented here**, so they are named and left alone.
Two whole containers are not on a page's list for the same kind of reason:
`STADIUMS.DAT` is 197 MB — past this module's 144 MB read limit — and its 2,914
members are 1,880 `SMF` and 1,034 empty, so there is no texture in it to edit;
`MOVIEDAT.DAT` is 333 MB of movie streams. Both are listed by the All Textures
page with their size.

Two kinds of `MMAP` entry are also refused **by name** rather than drawn wrong:
a **palette-only** entry, which carries an alternate CLUT for another image and
has no pixels of its own, and one that **declares no palette** and so is not an
indexed texture. Sampling 60 members per container [M]: `UIS_GEAR.DAT` draws
60 of 60, `PLADATA.DAT` 47 of 79 (20 palette-only, 12 with no palette), and
`UNIFORM.DAT` 780 of 840 — its members carry about thirteen drawable images each
plus one palette-only entry holding twelve alternate CLUTs.

---

## 4. The per-container target share, and why it exists

A flat cap on how many targets a catalogue lists is right until the first
container spends it. `UNIFORM.DAT`'s 1,200 members carry about **15,600 images**
between them [M], so a 4,000-target cap listed part of one container and **none
of `UIS_GEAR.DAT`'s 396** — the one container on this disc a user should reach
first, because no cache names it.

`TerfArtLane.max_targets_per_container` is the fix and the uniforms rows set it
to 1,500. It is on the shared base rather than in this module because the same
shape will bite the next disc: a container's share of a table is a property of
how art containers are laid out, not of NCAA Football.

---

## 5. The PCSX2 replacement identity: two frames confirmed, the rest derived

A replacement filename is `<tex0 hash>-<clut hash>-<bits>.png`, and both hashes
are computed by the emulator at draw time. No disc file carries either, so
`tools/ps2_texture_identities.py --game ncaa09_ps2` learns them by pairing a
texture dump with the disc on **exact pixel equality** — the same tool, and the
same matcher, that Madden 09's five art rows use.

**The corpus is two frames**, both from the owner's own capture of the retail
`SLUS-21752` disc (PCSX2 ELF CRC `B0157E6C`), replayed headless through
pcsx2-gsrunner with texture dumping on, each frame dumped under both naming
conventions — `ClassicTextureNames` on and off [M]:

| frame | what it shows | textures it named |
|---|---|---:|
| `20260905142332` | a midfield fumble, both kits and the end zone on screen | 495 |
| `20260905142337` | a helmet-camera close-up of one player | 468 |

That is 1,458 PNG files, **1,100 distinct names**, of which 188 are region
draws — a name carrying `-r<W>x<H>` is a sub-rectangle of a larger texture and
cannot equal a whole surface on the disc unless the region is the whole of one.
Against them the index decoded **40,085 surfaces** in the twelve art containers,
covering **16,308 distinct textures** (`container:member:image`).

**Result: 268 dumped files paired, naming 510 disc textures** [M]. Thirty-four
more agreed on RGB and not on alpha and are listed as near misses rather than
matched — `TCC` lets the game ignore a CLUT's alpha, so that is a real reason
for two to differ and not a reason to guess.

### Coverage per container [M]

The last column is measured, not guessed: it is how many of the two frames were
drawing at least one texture of that container when PCSX2 dumped them. What
those textures *depict* is not established by any of this.

| container | textures indexed | named | frames that drew one |
|---|---:|---:|---:|
| `UNIFORM.DAT` | 10,941 | 476 | 2 of 2 |
| `STADATA.DAT` | 1,224 | 17 | 2 of 2 |
| `FLDDATA.DAT` | 35 | 9 | 2 of 2 |
| `PLYRFACE.DAT` | 64 | 5 | 2 of 2 |
| `PLADATA.DAT` | 691 | 3 | 2 of 2 |
| `MSCTDATA.DAT` | 1,920 | 0 | none |
| `UIS_GEAR.DAT` | 396 | 0 | none |
| `UIS_TMLO.DAT` | 399 | 0 | none |
| `FANDATA.DAT` | 342 | 0 | none |
| `UIS_STAD.DAT` | 244 | 0 | none |
| `LOADDATA.DAT` | 34 | 0 | none |
| `COACFACE.DAT` | 18 | 0 | none |

**510 of 16,308 textures have a confirmed name — 3.1%.** That is a fact about
the capture, not about the disc: both frames are one matchup in progress, so
they reach the kits, the field, the stadium bowl, the equipment and a face, and
**seven of the twelve containers were drawn by neither frame** and have no
confirmed name at all. `replacement_identity` falls back to the derived name
for those, and `identity_note` says the name was computed rather than observed.

Two more honesties about the 476 in `UNIFORM.DAT`. They come from **66
distinct pictures** — 178 filenames across the two conventions — spread over
**243 of that container's 1,200 members**, and **466 of the 476 are a
picture more than one member carries** — one dump in this corpus equals the same
surface in 182 members. That is not a mistake and it is not padding: PCSX2 names
a texture after its pixels, so one replacement file covers every member that
carries the picture, and the table says on each row how many others it shares
with. Only **10** of the 476 are a picture unique to their member.

### What the two frames could not reach, and which screens would

Each of these would confirm a container that today has nothing [A] — the
capture is the owner's, and which screen draws what is a prediction until a
frame proves it:

| capture this | reaches | why it is worth doing first |
|---|---|---|
| the equipment / gear select screen | `UIS_GEAR.DAT` (396) | the one container **no preload cache names**, so it is the cheapest thing on the disc to rewrite |
| a school-logo menu (team select, schedule) | `UIS_TMLO.DAT` (399) | 399 school marks, and the Field Art page's other half |
| the stadium select screen | `UIS_STAD.DAT` (244) | a directory copy and no member copy — nearly free to rewrite |
| a loading screen, dumped while it is up | `LOADDATA.DAT` (34) | 30 of its 46 members are 854×480 full-screen art |
| a mascot, trophy or celebration cut-scene | `MSCTDATA.DAT` (1,920) | the largest unreached container on the disc |
| a sideline or coach close-up | `COACFACE.DAT` (18) | 18 textures, and the smallest container to finish outright |
| a wide crowd or blimp camera | `FANDATA.DAT` (342) | the helmet-cam frame has stands behind it and named **no** `FANDATA` texture, so which container draws the crowd is worth settling |
| **more matchups**, and a second stadium | `UNIFORM.DAT`, `STADATA.DAT` | one matchup reached 243 of 1,200 kit members; another two schools reach another set |

### The derivation, checked against the dump [M]

`derive_texture_names` computes both hashes from the texture's own bytes — the
GS block image of each mip chain and the image's own palette — through
`mod_editor/games/_formats/pcsx2_texture_name.py`. Every name this disc offers
for a texture no frame drew comes from that rule, so the rule itself was checked
against the names the emulator really wrote:

* **1,094 of the 1,106** dumped names whose PSM matches the surface they paired
  with are **reproduced** from the disc bytes, and **500 of the 510** identities
  have at least one name reproduced.
* The **CLUT half agrees on all 1,106**: 1,093 hash the image's own palette and
  13 an alternate palette the same member carries. None needed a palette the
  member does not have.
* **88 further names disagree on PSM** — the dumped name says 4-bit where the
  surface is 8-bit, or the reverse. Those are not errors: the matcher pairs a
  dump with every surface that draws the same picture, and a picture can exist
  at both depths, so the name belongs to the sibling surface.
* **12 names are not reproduced**, and all twelve are on **six members of
  `FLDDATA.DAT`** (75, 76, 79, 80, 81, 82), every one of them 4-bit. On each of
  the six the dumped CLUT hash, the dumped `bits` word and the decoded picture
  all agree with the member, and only the `TEX0` half differs. The member's
  palette holds sixteen distinct colours, so the index bytes are forced by the
  picture and the two sides are hashing the same bytes in a different order.
  **Four of the twelve are now explained, and eight are not** [M]:

  * All six are `mip_count == 1` members standing in a **run of consecutive
    members that halve under one palette** — 75, 76, 77, 78 are 64×64, 32×32,
    16×16 and 8×8 under CLUT `e00d7b51…`, and 79 … 84 are 128×64 down to 8×4
    under CLUT `da1d61f0…`. That is one texture's mip pyramid stored as several
    members, and PCSX2 feeds every level of the draw's LOD range into **one**
    hash state, so a member hashed on its own reproduces none of the run's
    names. The check now walks that chain automatically.
  * For the first run it reproduces the names **exactly**: member 75's name is
    the hash of members 75+76+77+78 in order, and member 76's is 76+77+78. The
    earlier reading of this page — that the chain hypothesis was tested and
    refused — was tested on members 79…82 only, and those are not the whole
    run; the two members that carry its 16×16 and 8×8 levels were not in it.
  * For the second run **no chain reproduces anything**. Every contiguous
    sub-range of members 79…84, in both directions, under four readings of each
    level's bytes (block image, linear one byte per texel, packed nibbles, the
    stored bytes as they sit), was hashed and none of the four names came back
    [M]. The 8×4 tail is the suspect — it is the one level the first run does
    not have, its stored block is 32 bytes for 16 bytes of texels, and every
    chain of this run passes through it — but that is a hypothesis and not a
    measurement. **Eight names remain unexplained**, and this stays a finding
    about the derivation, not about the dump.

**Which GS modes this dump actually used** [M]. An 8-bit texture a game uploads
as the *high-byte* `PSMT8H` surface is hashed by PCSX2 over the plain linear
texel stream rather than the block image, so it has a different `bits` word
**and** a different TEX0 hash from the same pixels drawn as `PSMT8` — a
distinction that cost MVP Baseball 2005's census 1,035 names before it was
known. The check now tries that second reading for every 8-bit surface and
records the mode of every dumped name it saw:

| GS pixel mode | names checked | TEX0 reproduced | not reproduced | names of a mode this surface has none |
|---|---:|---:|---:|---:|
| `PSMT8` (19) | 124 | 124 | 0 | 88 |
| `PSMT4` (20) | 982 | 970 | 12 | 0 |
| `PSMT8H` (27) | 0 | 0 | 0 | 0 |
| **total** | **1,106** | **1,094** | **12** | **88** |

**Not one of the 1,100 names this dump wrote declares PSM 27**, so the second
reading had nothing to answer and no count above moved when it was added. That
is also why the art lanes leave `extra_psms` empty: offering a high-byte name
for every 8-bit texture would be a claim about how this game draws that nothing
on this disc supports.

Across the whole disc the same rule names **17,183 of 19,596 images** in 35
containers, 235,722 names in all; the 2,413 it will not name are palette-only
entries (979), mip chains that do not halve (751), textures whose width or
height is not a power of two (447), members that declare no palette at all (234)
and two whose level 0 could not be read [M]. Running those derived hashes back
against the dump places **309 of the 617 plain dumped names**, including **161
the pixel matcher could not place** — so the derivation reaches textures the
pixel pairing missed, and neither method is a superset of the other.

The measured tables are
`docs/product/measured/ncaa09_ps2/pcsx2-texture-identities.json` and
`docs/product/measured/ncaa09_ps2/pcsx2-texture-identity-derivation.json`. They
carry names, counts, dimensions and member indexes — **no pixel**.

**No pack built from any of these names, confirmed or derived, has been loaded
in an emulator**, so *Write PCSX2 pack* is still offered from no row.

---

## 6. What was proved on the retail disc

Five of the six were run by hand on the owner's own image; the numbers are also
in [`NCAA09_PS2_MODULE.md`](NCAA09_PS2_MODULE.md) §3a. Each replaced one texture
with a **flip of itself**, which is exactly representable — every pixel of a flip
is a colour the texture's own palette already holds, so the check that the edit
landed is about the write rather than about quantisation.

| row | member | size | untouched members | cache copies re-read | image | verdict |
|---|---|---|---:|---:|---|---|
| `rosters.face_textures` | `PLYRFACE.DAT:16:0` | 128×128 | 79 | **74** | unchanged | PASS |
| `stadiums.textures` | `UIS_STAD.DAT:0:0` | 128×128 | 244 | 1 | unchanged | PASS |
| `uniforms.disc_art_writer` | `UIS_GEAR.DAT:0:0` | 128×128 | 395 | **0** | unchanged | PASS |
| `field_art.textures` | `UIS_TMLO.DAT:0:0` | 128×128 | 398 | 9 | **grew 428 sectors** | PASS |
| `presentation.ui_textures` | `FANDATA.DAT:12:0` | 128×128 | 256 | 1 | unchanged | PASS |

`UIS_GEAR.DAT`'s zero is the point of that row: no cache names it, so nothing
had to move with the edit. `PLYRFACE.DAT`'s 74 is the other end — the path where
a stale copy would silently win, exercised on real bytes.

`UIS_TMLO.DAT` is the one that grew: the flipped logo re-packed under `LZH1`
past the extent that container owns, so the ISO writer relocated the file and
the image went from 2,175,041,536 to **2,175,918,080** bytes. That is why every
art row declares `fixed_allocation = False`: keeping the length is the ordinary
outcome and not a promise, and the receipt carries the number either way. In the
other four the destination came back the source's exact size.

In all five the texture decoded out of the new image as the PNG that was given,
and an adversarial flip of one byte outside every declared range was refused.

**No rebuilt NCAA Football 09 container has been booted.** That the game loads
any of this is not claimed on any page, in any receipt, or in any registry row.

---

## 7. Where the code is

```
mod_editor/games/_formats/mmap_art.py            the pixel codec, shared
mod_editor/games/_formats/pcsx2_texture_name.py  the GS hashes
mod_editor/games/_lanes/terf_art.py              TerfArtLane, TerfArtWriteLane
mod_editor/games/_lanes/preload_coherence.py     the cache rule
mod_editor/games/_lanes/synthetic_art.py         the fixtures both games use
mod_editor/games/ncaa09_ps2/texture_lane.py      the two uniforms rows
mod_editor/games/ncaa09_ps2/art_pages.py         the other four
tools/ps2_texture_identities.py                  the dump/disc pixel matcher, both games
tools/madden09_ps2_texture_identities.py         the same tool, --game madden09_ps2
tools/validate_ncaa09_ps2_textures.sh            the census row
tools/validate_ncaa09_ps2_uniform_disc_art.sh    the uniforms writer
tools/validate_ncaa09_ps2_art_pages.sh           the other four, in one run

docs/product/measured/ncaa09_ps2/pcsx2-texture-identities.json
docs/product/measured/ncaa09_ps2/pcsx2-texture-identity-derivation.json
tests/mod_editor/test_ncaa09_ps2_texture_identities.py
```

```
python3 -m mod_editor.games.ncaa09_ps2.texture_lane --source "<your>.iso" \
    --export OUT/manifest.json --limit 24
python3 -m mod_editor.games.ncaa09_ps2.art_pages --page stadiums \
    --source "<your>.iso" --out catalogue.json
python3 -m mod_editor.games.ncaa09_ps2.art_pages --selftest
python3 tools/ps2_texture_identities.py --game ncaa09_ps2 --selftest
python3 tools/ps2_texture_identities.py --game ncaa09_ps2 --source "<your>.iso" \
    --index disc-index.jsonl --dump-dir "<PCSX2 textures/dumps>" --coverage \
    --out docs/product/measured/ncaa09_ps2/pcsx2-texture-identities.json
python3 tools/ps2_texture_identities.py --game ncaa09_ps2 --source "<your>.iso" \
    --derive-check
```
