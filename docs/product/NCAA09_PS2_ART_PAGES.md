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

## 5. The PCSX2 replacement identity: derived, never confirmed

Naming a texture so PCSX2's replacement picks it up needs the GS `TEX0` and CLUT
hashes the emulator computes at draw time. `derive_texture_names` computes both
from the texture's own bytes — the GS block image of each mip chain and the
image's own palette — through
`mod_editor/games/_formats/pcsx2_texture_name.py`.

**No PCSX2 texture dump has been paired with `SLUS-21752`.** So every name these
six rows offer is **derived** and none is **confirmed**, and
`identity_note` says which. Madden 09 has a paired dump and an identity document
(`docs/product/measured/madden09_ps2/pcsx2-texture-identities.json`); this game's
`identity_document` is `None`, which is the honest value — a document that does
not exist is not a document to read.

**Pairing one dump with this disc is the single cheapest thing that lifts all six
rows at once.** Until then, *Write PCSX2 pack* is not offered from any of them,
and no pack built from these names has been loaded in an emulator.

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
tools/validate_ncaa09_ps2_textures.sh            the census row
tools/validate_ncaa09_ps2_uniform_disc_art.sh    the uniforms writer
tools/validate_ncaa09_ps2_art_pages.sh           the other four, in one run
```

```
python3 -m mod_editor.games.ncaa09_ps2.texture_lane --source "<your>.iso" \
    --export OUT/manifest.json --limit 24
python3 -m mod_editor.games.ncaa09_ps2.art_pages --page stadiums \
    --source "<your>.iso" --out catalogue.json
python3 -m mod_editor.games.ncaa09_ps2.art_pages --selftest
```
