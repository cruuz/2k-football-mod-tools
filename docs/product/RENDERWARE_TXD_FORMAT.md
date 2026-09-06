# RenderWare `.rtd` — the texture dictionary both NFL Blitz discs keep their art in

NFL Blitz 2002 (`SLUS-20051`) and NFL Blitz 2003 (`SLUS-20474`) keep **every**
texture in a RenderWare binary stream whose one top-level section is a
**texture dictionary**, section id `0x16`: 761 such members on the 2002 disc and
840 on the 2003 disc, holding 10,420 and 11,828 PlayStation 2 native rasters
[M]. Nothing else on either disc is art: the member census of both archives
lists no `MMAP`, no `SHPS` and no `TSET`, and the only other RenderWare on
either disc is 2,708 `.dff` clump streams, which are geometry (§2.1) [M].
Midway wrote no variant — the ids are RenderWare's own and the library version
words are RenderWare 3.x [M].

The implementation is `mod_editor/games/_formats/rw_txd.py` (pure Python,
Qt-free, standard library only), with `tests/mod_editor/test_formats_rw_txd.py`
covering it on **synthetic dictionaries only** — 14 tests, every byte built by
`rw_txd.build_synthetic_dictionary`.

**Evidence tags.** **[M]** measured by running this module against a disc this
project can reach. **[S]** sourced. **[A]** assumed — a question, not a fact.

**Retail-free.** Constants, offsets, counts, section ids, library versions and
refusal sentences. No pixel, no palette entry and no texture name from any disc
is reproduced here.

---

## 1. The verdict, in six sentences

1. **The container is fully decoded** [M]: the section-chunk stream, the
   dictionary, the `TextureNative`, the 64-byte PS2 raster header and its two
   GIF-tagged GS uploads, with zero counter-examples across all 1,601
   dictionaries and all 22,248 rasters of the two Blitz discs. Every identity
   the file states about itself holds on every raster (§3).
2. **The GS layout was measured, not assumed, and that measurement is the whole
   document** (§5). 8-bit `PSMCT32` composition scored **7.32** against
   **24.26** for reading the bytes linearly — **232% better** — and is taken.
   **No 4-bit candidate separates**: the best scored 18.75 against the null's
   20.53, 9%, which is noise. So **6,231 rasters on the 2002 disc and 5,436 on
   the 2003 disc are listed with their size, format and GS pixel mode and are
   not drawn**, and those two numbers are the reason the refusal gives.
3. **The score is one number and §5.2 says how to recompute it**, so the next
   reader can re-run the comparison instead of trusting it.
4. **A raster's PCSX2 replacement identity is derived and none is confirmed**
   (§6). No texture dump of either Blitz disc exists in this project; the name
   is what the emulator's documented rules compute from the raster's own bytes,
   through `pcsx2_texture_name`, whose GS block layout is measured against 33
   dumps *of a different game*.
5. **A same-length texture writer is within these readers and is not offered**
   (§8). `rw_txd._swizzle8` is the exact inverse of the decode and the synthetic
   builder already round-trips through it — which makes the writer cheap and
   **unproved**, and unproved is not shipped.
6. **This reader is not Blitz-specific, and §9 measures what else it opens**:
   NFL Blitz Pro and Blitz: The League read with the same code and no change,
   and Madden NFL 06's only RenderWare — a bundled Burnout 3 demo — holds no
   texture dictionary at all and is refused by five distinct sentences.

---

## 2. The section-chunk stream [S: RenderWare's published binary-stream grammar]

A RenderWare stream is a tree of sections, each one twelve bytes of header and
then a body that is either payload or more sections:

```
+0x00  u32  section id
+0x04  u32  body bytes          -- the body only; it does NOT include this header
+0x08  u32  library version     -- a packed RenderWare version word
+0x0C  body bytes
```

The ids this module names [S], and what carries them on a Blitz disc [M]:

| id | name | where |
|---:|---|---|
| `0x01` | `Struct` | the dictionary's count, a `TextureNative`'s platform word, the raster header, the raster data |
| `0x02` | `String` | a texture's name and its mask name |
| `0x03` | `Extension` | present and empty at every level measured |
| `0x15` | `TextureNative` | one per raster |
| `0x16` | `TextureDictionary` | the one top-level section of a `.rtd` |

```
0x16  TextureDictionary : Struct(u16 textures, u16 device), N x 0x15, Extension
0x15  TextureNative     : Struct(platform, flags), String name, String mask name,
                          Struct raster, Extension
      raster            : Struct(64-byte header), Struct(GIF-tagged GS upload)
```

`rw_txd.walk(data, start, end)` is the whole grammar: it yields sections laid
end to end and **stops rather than raising** when a declared length runs past
`end`. A stream's tail is the caller's business, and every identity this module
checks is stated over what the walk returned.

### 2.1 Why a `.dff` fails a single-section length rule and a `.rtd` passes it

The owner's disc map classified all 2,708 `.dff` members of the two discs as a
raw magic, because the rule it applies to a container — `section bytes + 12 ==
the file` — fails on every one of them [S: `docs/owner/disc_maps/`]. The rule is
not wrong about RenderWare; **it is the wrong rule for a multi-section file**
[M]:

| | `.rtd` (texture dictionary) | `.dff` (clump) |
|---|---|---|
| top-level sections | exactly **one**, id `0x16` | **one or two**: `Clump(0x10)` then `Extension(0x03)`, or `Clump` alone |
| `body + 12 == the file` | holds, **761 of 761** and **840 of 840** [M] | fails on all 2,708 [M] |
| a walk over the whole member consumes it exactly | 761 / 840 | 1,043 of 1,272 and 1,167 of 1,436 [M] |
| top-level sequence census | `0x16` on every one | `0x10 0x03` on 1,043 and 1,145; `0x10` alone on 162 and 149 [M] |
| library version words | `0x0401ffff` on every dictionary [M] | `0x0401ffff` 680 / 843 and `0x00000310` 592 / 593 [M] |

So `Dictionary.section_accounts_for_file` is reported and never required: a
dictionary that does not account for its member is still read, and the flag says
which kind it was. The clump walk lives on the presentation row of both modules
(`walk_clump`), and **a clump's geometry, materials and frames are not read**
(§10).

---

## 3. The dictionary and the `TextureNative` [M]

`read_dictionary(data, name)` refuses anything whose own words do not hold, and
each refusal is one sentence naming the condition (§11). What it checks, and
what the two discs answer:

| identity | 2002 | 2003 |
|---|---:|---:|
| the first section is id `0x16` | 761 of 761 | 840 of 840 |
| that one section plus its header is the whole member | 761 | 840 |
| the dictionary's `Struct` declares a `u16` texture count | 761 | 840 |
| that count equals the `TextureNative` sections found | 10,420 | 11,828 |
| every `TextureNative` carries ≥ 4 sections | 10,420 | 11,828 |
| its first `Struct` begins with the platform word `PS2\0` | 10,420 | 11,828 |
| it carries two `String` sections (name, mask name) | 10,420 | 11,828 |
| its second `Struct` is the raster | 10,420 | 11,828 |
| library version word | `0x0401ffff` on all 761 | on all 840 |

Two bounds keep a corrupt word from allocating: a member larger than
`_MAX_MEMBER_BYTES` (64 MB) is refused before the walk — the largest dictionary
on either disc is **1.1 MB** [M] — and a dictionary declaring more than
`_MAX_RASTERS` (4,096) textures is refused — the largest on either disc declares
**244** [M].

A name is read as **Latin-1 up to its first NUL** inside the `String`'s
declared span. Latin-1 never fails and never invents a byte; the padding after
the NUL is the writer's buffer, not text.

---

## 4. The PS2 raster [M]

The raster `Struct` holds exactly two children: a **64-byte header** and one
**data section**. The header is decoded word by word against the GS registers it
carries [M]:

```
+0x00  u32  width               +0x10  u64  TEX0     (GS register)
+0x04  u32  height              +0x18  u64  TEX1     (GS register)
+0x08  u32  depth, bits/texel   +0x20  u32  MIPTBP1
+0x0C  u32  raster format flags +0x28  u32  MIPTBP2
                                +0x30  u32  texel section bytes
                                +0x34  u32  palette section bytes
                                +0x38  u32  GPU-aligned bytes
                                +0x3C  u32  (unnamed)
```

The arithmetic that makes this a reading rather than a guess:

* **`texel bytes + palette bytes == the data section's body`**, on 10,420 and
  11,828 rasters [M]. The reader refuses a raster where it does not hold, by
  sentence, because nothing after that point is safe to read.
* **`TEX0`'s `TW`, `TH` and `PSM` agree with the header's own width, height and
  depth**, on 10,420 and 11,828 [M]. `TW`/`TH` are logarithms — `1 << ((tex0 >>
  26) & 0xF)` and `1 << ((tex0 >> 30) & 0xF)` — and `PSM` is `(tex0 >> 20) &
  0x3F`. Two independent statements of the same size agreeing 22,248 times is
  what says the header is being read at the right offsets.

### 4.1 The GS pixel modes in play [S: the GS's storage modes]

| depth | `PSM` | name | 2002 | 2003 |
|---:|---:|---|---:|---:|
| 8 | 19 | `PSMT8`, 8-bit indexed | 4,166 | 6,365 |
| 4 | 20 | `PSMT4`, 4-bit indexed | 6,231 | 5,436 |
| 32 | 0 | `PSMCT32`, direct colour | 23 | 27 |

Those three are the whole population on both discs [M]; a fourth depth is
refused with a sentence that says so.

### 4.2 The raster format flags

The `u32` at +0x0C is RenderWare's raster-format word. Three bits are read [S]:

| bit | name | meaning |
|---:|---|---|
| `0x2000` | `PAL8` | the raster is 8-bit indexed and carries a 256-entry CLUT |
| `0x4000` | `PAL4` | 4-bit indexed, 16-entry CLUT |
| `0x8000` | `MIPMAP` | the raster declares a mip chain |

The low half of the word is a pixel-format enumeration this module does not
interpret [A]; it is carried on every catalogue row as `raster_format` so a page
can show it. **It is `0x504` on every raster of every disc measured** — 22,248
on the two Blitz discs and 22,533 more on the two later ones (§9.2) — so the
only bits that ever vary are the three above, and the whole census of the word
is five values [M]:

| word | 2002 | 2003 | what it is |
|---|---:|---:|---|
| `0x2504` | 3,999 | 6,225 | `PAL8` |
| `0x4504` | 5,541 | 4,788 | `PAL4` |
| `0xa504` | 167 | 140 | `PAL8` + `MIPMAP` |
| `0xc504` | 690 | 648 | `PAL4` + `MIPMAP` |
| `0x0504` | 23 | 27 | direct colour, no palette flag |

The palette flag and the header's own `depth` never disagree, on any raster of
any disc [M].

### 4.3 The GIF chain, which is where the pixels actually are

The data section is **not** a raster; it is a recording of the DMA the game
replays to upload the texture to GS memory. It is a GIF chain [S: the GS's GIF
packet format]:

```
GIF tag   u64 low, u64 regs        16 bytes
          NLOOP  = low & 0x7FFF
          FLG    = (low >> 58) & 3      0 = PACKED, 1 = REGLIST, 2 = IMAGE
          NREG   = (low >> 60) & 0xF
```

Both discs write the same two-packet shape [M]: a `PACKED` A+D packet setting
`TRXPOS` (`0x51`), `TRXREG` (`0x52`) and `TRXDIR` (`0x53`), then an
**`IMAGE`-mode tag whose `NLOOP * 16` bytes are the upload itself**.
`_gif_image_payload` walks the chain, skips a `PACKED` packet by
`NLOOP * NREG * 16` bytes (`NREG` of 0 meaning 16, as the GIF tag defines it
[S]), and returns the first `IMAGE` payload's `(offset, length)`; a `REGLIST`
packet, or a chain with no `IMAGE` tag in it, ends the walk and the raster is
refused by sentence. That never happens on either Blitz disc — 22,248 of 22,248
rasters yield an `IMAGE` payload [M] — and happens twice on NFL Blitz Pro
(§9.3).

**The upload is the GS's memory image, not the texture.** The `TRXREG`
rectangle is *not* the texture's size: an 8-bit texture is transferred as
`PSMCT32` at **half its width and half its height** (four 8-bit texels ride in
one 32-bit word) and a 4-bit one as `PSMCT16` at the same halved size. So the
bytes on the disc are laid out the way the GS stores them and have to be
un-swizzled — which is §5, and is the only part of this format that was ever in
doubt.

### 4.4 Mip levels

`Raster.has_mipmaps` reports the `0x8000` flag and **nothing decodes a level
below zero** [M]. `decode_indices` asks the GIF payload for exactly
`width * height` bytes, which is level 0, and refuses if the upload carries
fewer. `MIPTBP1` / `MIPTBP2` — the GS registers that give levels 1–6 their base
pointers and buffer widths — are read into the header dataclass and are **not
interpreted** [A]. §9 counts how many rasters set the flag on each disc; a page
that wanted level 1 would start at those two registers and at the bytes past
`width * height` in the same payload.

---

## 5. The GS layout, which is the centre of this document [M]

### 5.1 The measurement, and the two numbers that decide it

Seven candidate un-swizzles were scored on **30 rasters of the retail 2002
disc**. Lower is more coherent; the winner is bold and the null — reading the
upload's bytes as if they were already the linear texture — is the row every
other row has to beat:

| depth | candidate layout | score | against the null |
|---|---|---:|---|
| 8-bit | **`PSMCT32` composition** | **7.32** | **232% better — taken** |
| 8-bit | GS block image, inverted | 15.93 | 52% better |
| 8-bit | raw linear (**the null**) | 24.26 | — |
| 4-bit | half-width via the 8-bit routine | 18.75 | 9% better |
| 4-bit | the published 4-bit routine | 20.14 | 2% better |
| 4-bit | raw linear (**the null**) | 20.53 | — |
| 4-bit | GS block image, inverted | 28.16 | 37% **worse** |

**The 8-bit answer is taken. No 4-bit candidate separates from its null**, so
`decode_rgba` refuses a 4-bit raster by name and the refusal quotes both numbers:

> A 4-bit raster's GS upload layout is not established: seven candidate
> un-swizzles were scored on the retail disc and the best beat reading the bytes
> linearly by 9%, where the 8-bit answer beat it by 232%, so this reader lists a
> 4-bit raster and does not draw it.

That is **6,231 rasters on the 2002 disc and 5,436 on the 2003 disc listed and
not drawn** [M] — 60% and 46% of each disc's art. Those two counts are the
price of the negative result, and they are printed on the page rather than
hidden, because a half-right picture exported as if it were the texture is how a
modder ships a corrupted logo.

**The assumption that would make the negative wrong.** The score assumes a
*correctly* un-swizzled 4-bit raster is locally coherent in the same way an
8-bit one is — that horizontally adjacent decoded pixels differ little. A 4-bit
image is 16 colours, so its palette steps are large and its neighbour
differences are large even when the layout is right; on a disc whose 4-bit art
is mostly flat-shaded UI panels the true layout might score only a little under
the null and be discarded here for want of contrast, not for want of
correctness. The test that settles it is not a better score — it is an **answer
key**: one PCSX2 texture dump of either Blitz disc, whose decoded texels can be
compared to each candidate directly. No such dump exists in this project (§6).

### 5.2 What the score is, and how to recompute it

The score is the **mean absolute difference between horizontally adjacent
decoded RGB values**, over a sample of rasters, one number per candidate
layout. For a decoded image of width `w` and height `h`:

```
score = mean over all y in [0, h), x in [0, w-1) of
        ( |R(x+1,y) - R(x,y)| + |G(x+1,y) - G(x,y)| + |B(x+1,y) - B(x,y)| ) / 3
```

Alpha is excluded. Real art is locally coherent — a photograph, a logo, a jersey
sheet all have neighbouring pixels of nearly the same colour — and **a wrong
layout destroys that** by scattering pixels from elsewhere in the image into
each row. The null is the same statistic over the upload's bytes read as a
linear raster, so the comparison is layout-against-no-layout on identical
pixels, palette and sample.

To re-run it: take a sample of rasters of one depth, decode each under each
candidate, compute the statistic, and average over the sample. The candidates
scored were the `PSMCT32` composition (§5.3), the GS block image with the
permutation inverted (`pcsx2_texture_name.block_image`), the raw linear
reading, and — for 4-bit — the half-width-through-the-8-bit-routine reading and
the published 4-bit routine. The numbers above are recorded in
`docs/product/measured/nflblitz2002_ps2/texture-dictionaries.json` under
`gs_layout_measurement`, with the method in the same object.

### 5.3 The composition that was taken

`_unswizzle8(gs, width, height)` is the inverse of "upload this 8-bit texture as
a `PSMCT32` rectangle of half its width and half its height". For each output
pixel `(x, y)` it reads the source byte at

```
(y & ~0xF) * width                       -- the 16-row band
+ (x & ~0xF) * 2                         -- the 16-column band, doubled
+ ((((y & ~3) >> 1) + (y & 1)) & 7) * width * 2
+ ((x + (((y + 2) >> 2) & 1) * 4) & 7) * 4
+ ((y >> 1) & 1)                         -- the parity byte inside the word
+ ((x >> 2) & 2)
```

and a source index past the end of the payload yields 0 rather than an error,
so a short upload degrades to a dark corner instead of a crash. It is a byte
permutation and nothing else: no interpolation, no filtering, no colour-space
step. **`_swizzle8` is its exact inverse** and §8 is what that does and does not
buy.

### 5.4 The palette

`read_palette(dictionary, raster)` returns the CLUT in **drawing order**, RGBA,
one 4-tuple per entry:

* the palette lives in its **own GIF chain**, at `data_offset + texel_bytes`,
  and is read with the same `IMAGE`-mode walk;
* the upload rectangle is **wider than the palette needs** — `8 x 3` for sixteen
  entries and `16 x 16` for 256 [M] — and the entries the texture unit reads are
  the first `2 ** depth`; a reader that took the entry count from the payload
  length would build a palette with junk on the end;
* **a 256-entry CLUT is in the GS's CSM1 interleave and is put back** [S: the
  GS's CLUT storage]: within each group of 32 entries the second group of eight
  and the third are exchanged. `_deinterleave_csm1` is its own inverse, which is
  what the synthetic builder relies on to write a palette back into storage
  order. A 16-entry CLUT is **not** interleaved, and the reader applies the swap
  at exactly 256 entries and nowhere else.
* **Alpha is the GS's own scale**, where `0x80` is opaque, not `0xFF` — the
  same convention EA's PS2 art uses, because it is a fact about the console and
  not about either publisher. `read_palette` and `decode_rgba` hand back the
  **stored** byte and widen nothing; a consumer that wants 0–255 alpha widens it
  itself, and a PCSX2 dump matcher wants the stored form.

A 32-bit raster carries **no** palette and `read_palette` refuses it by
sentence; a `decode_rgba` of one returns the GIF payload's first
`width * height * 4` bytes with no index step.

---

## 6. From a decoded raster to a PCSX2 replacement identity

PCSX2 finds a replacement texture by a filename it builds while the game draws:
`<tex0 hash>-<clut hash>-<bits>.png`, both hashes XXH3-64 [S]. The TEX0 half is
over the texture's **GS block image** — the emulator walks the texture's
256-byte blocks in row-major block order and hashes each block's bytes as the GS
stores them — and the CLUT half is over the palette in drawing order.

`rw_txd.replacement_identity(dictionary, raster)` is those rules over a
raster's own bytes, and it is deliberately narrow:

1. it answers `None` for anything `undecodable_reason` names, and for any depth
   but 8 — **a 4-bit or 32-bit raster gets no identity**;
2. it decodes the indices (§5.3) and the palette (§5.4), wraps level 0 as a
   `pcsx2_texture_name.TextureLevel(width, height, 8, indices)`, and takes
   `tex0_hash([level])`, `clut_hash(palette)` and
   `texture_bits(PSMT8, log2(width), log2(height))`;
3. a dimension that is not a power of two raises inside
   `pcsx2_texture_name.log2_exact` and the identity comes back `None` rather
   than wrong, because the GS `TW`/`TH` fields are logarithms and a hash over a
   non-power-of-two texture would cover memory the disc does not carry;
4. only the **single-level** name is derived. PCSX2 feeds the levels a draw can
   reach into the same hash state, so a mipmapped texture has one name per
   `(base level, level count)` pair the game happens to use, and none of those
   is computed here.

**Every identity this module returns is derived and none is confirmed** [M].
The rules are measured — `pcsx2_texture_name`'s GS block layout reproduces
2,994 of 3,024 dumped TEX0 hashes on a **Madden NFL 09** disc — but no PCSX2
texture dump of any Blitz disc exists in this project, so nothing here says the
emulator was seen to ask for one of these names. Counts per disc: **4,166**
identities derived on the 2002 disc and **6,365** on the 2003 disc [M], which is
exactly each disc's 8-bit raster count.

---

## 7. Reading

```python
from mod_editor.games._formats import ea_shps, rw_txd

book = rw_txd.read_dictionary(member_bytes, name="a texture dictionary")
book.declared_textures, book.library_version, book.section_accounts_for_file
raster = book.raster(0)
raster.width, raster.height, raster.depth, raster.psm, raster.has_mipmaps
rw_txd.undecodable_reason(raster)          # None, or one sentence
indices = rw_txd.decode_indices(book, raster)     # 8-bit only
palette = rw_txd.read_palette(book, raster)       # drawing order, GS alpha
rgba = rw_txd.decode_rgba(book, raster)
open("out.png", "wb").write(ea_shps.encode_png(raster.width, raster.height, rgba))
rw_txd.replacement_identity(book, raster)  # derived, never confirmed
```

`rw_txd` writes no PNG of its own: `ea_shps.encode_png` is thirty lines of
`zlib` and `binascii` and is shared rather than written twice.

`build_synthetic_dictionary([(name, width, height, indices, palette), ...])`
builds a complete dictionary byte by byte — section headers, the platform word,
both `String`s, the 64-byte header with a consistent `TEX0`, both GIF chains,
the CSM1-ordered CLUT and the swizzled texel upload. Every byte comes from the
caller or from that function, which is what lets CI prove the decoder without a
disc.

---

## 8. What a writer would need

**A same-length 8-bit texture writer is within these readers today, and it is
not offered.** The three things it needs already exist and are proved in CI:

| step | what does it | proved by |
|---|---|---|
| pixels → palette indices | the caller's own quantiser, against the raster's existing CLUT | not written |
| indices → the GS memory image | `rw_txd._swizzle8`, the **exact inverse** of `_unswizzle8` | the synthetic builder lays known pixels through it and a decode returns them exactly, in CI |
| the member back onto the disc | `blitz_zip.plan_member_replacement` — same length, every CRC-32 site | `MIDWAY_ZIP_FORMAT.md` §6, and four chained builds on each retail disc |

What would still have to be got right, and is not:

* **the payload's length must not change**, which means the same width, height,
  depth and mip-flag as the raster already has — the header's `texel bytes`,
  `palette bytes` and `GPU-aligned bytes` words and the GIF tag's `NLOOP` are
  all length statements about the same bytes, and a writer that changed the size
  would have to move every one of them and the data section's own `body bytes`;
* **the palette**, if it is rewritten, goes back through the CSM1 interleave
  (`_deinterleave_csm1` is its own inverse) and must stay `2 ** depth` entries
  inside the same oversized upload rectangle;
* **alpha is the GS scale** — writing `0xFF` where the disc wants `0x80` is a
  silently wrong texture, not an error;
* **a 4-bit raster cannot be written at all**, because §5 says the layout is not
  established: an inverse of a layout that was never established is not an
  inverse of anything;
* **nothing has been booted.** No image carrying a rewritten raster has been run
  in an emulator or on hardware, so even a byte-perfect writer would be
  `offline-writer-proved` at best.

That is why both Blitz modules' art rows are `extract-only` and their `encode`
refuses by name. The distance from here to a writer is a quantiser and a proof,
not a format question.

---

## 9. What else this reader opens: five discs, measured

`docs/product/measured/rw_txd/cross-disc-census.json` is the whole census with
its counts, its refusal sentences and the method that produced it.

### 9.1 Every disc, side by side [M]

| | NFL Blitz 2002 | NFL Blitz 2003 | NFL Blitz Pro | Blitz: The League | Madden NFL 06 |
|---|---:|---:|---:|---:|---:|
| serial | SLUS-20051 | SLUS-20474 | SLUS-20631 | SLUS-21128 | SLUS-21213 |
| container the members live in | `BASSETS.ZIP` | `BERTHA.ZIP` | `RESIMG1.DAT` | `RESIMG1.DAT` | loose ISO9660 files |
| members examined | 2,426 | 2,695 | 5,605 | 7,409 | 178 |
| RenderWare-extension members | 2,033 | 2,276 | 3,870 | 4,541 | 132 |
| **dictionaries read** | **761** | **840** | **1,641** | **4,442** | **0** |
| dictionaries refused | 1,272 | 1,436 | 2,229 | 99 | 132 |
| **rasters read** | **10,420** | **11,828** | **17,609** | **4,924** | **0** |
| 8-bit / 4-bit / 32-bit | 4,166 / 6,231 / 23 | 6,365 / 5,436 / 27 | 3,202 / 14,407 / 0 | 3,303 / 1,620 / 1 | — |
| **rasters decoded to RGBA** | **4,189** | **6,392** | **3,200** | **3,304** | **0** |
| decoded, as a share of the disc's art | 40% | 54% | **18%** | **67%** | — |
| rasters listed and not drawn | 6,231 | 5,436 | 14,407 | 1,620 | — |
| **identities derived** | **4,166** | **6,365** | **3,200** | **3,303** | **0** |
| per-raster decode failures | 0 | 0 | **2** | 0 | — |
| library version, every dictionary | `0x0401ffff` | `0x0401ffff` | `0x1005ffff` | `0x1c020020` | — |
| where the leg ran | dev box | dev box | dev box | dev box | **NAS** |

Every dictionary on all four Blitz discs passes the same three identities [M]:
its one section accounts for the member (761 / 840 / 1,641 / 4,442), its
declared texture count equals the rasters found (same four numbers), and every
raster's `TEX0` agrees with its header's width, height and depth (10,420 /
11,828 / 17,609 / 4,924). **The reader was not modified for any of them.**

### 9.2 What the four Blitz discs say about the format itself [M]

The two discs the reader was written on are not the whole population, and three
things hold across all four:

* **The raster-format word's low half is `0x504` on every raster of every disc**
  — 22,248 on the two Blitz discs, 17,609 on Blitz Pro, 4,924 on The League.
  Only the palette and mipmap bits vary, which is what says §4.2 is reading the
  right bits.
* **The mipmap flag is set on a minority and level 0 is all anyone reads**: 857,
  788, 297 and 198 rasters [M]. §4.4 is a real gap on four discs, not two.
* **Three RenderWare generations, one reader.** `0x0401ffff` (Blitz 2002/2003),
  `0x1005ffff` (Blitz Pro) and `0x1c020020` (The League) are three different
  library versions across four years, and the section grammar, the 64-byte
  raster header, the GIF chain and the CSM1 CLUT are identical under all three.

The one thing that is **not** stable is how much of a disc comes out, and it is
entirely §5's 4-bit gap: **18% of Blitz Pro's art decodes and 67% of The
League's**. The reader is the same; the discs' art is not.

### 9.3 Blitz Pro's two refused rasters [M]

Two 8-bit rasters on NFL Blitz Pro — and none on any other disc — are refused
individually, after their dictionary read cleanly:

> raster 0's texel section carries no `IMAGE`-mode GIF tag; its pixels cannot be
> read.

Their data section carries a GIF chain the `IMAGE` walk does not reach: either
a `REGLIST` packet, which ends the walk by design, or a packet chain whose
`NLOOP` arithmetic runs past the section. Two of 17,609 is not a format
question, and the reader lists them rather than guessing [A].

### 9.4 Madden NFL 06: the RenderWare on it is not this format [M]

Madden NFL 06 is on this list because it is an EA title that carries
RenderWare, which is unusual enough to be worth measuring. It does — and **none
of it is a texture dictionary**.

The disc's own art is EA `TERF`/`MMAP` (10,405 `MMAP` members across 38
containers) and `SHPS` inside three `BIG` archives [S: the disc map]. The
RenderWare is a **bundled Burnout 3 demo** under `/BURNOUT`, 178 files, of which
132 carry a RenderWare extension. All 132 are refused, by five distinct
sentences [M]:

| first word | members | extensions | the sentence |
|---|---:|---|---|
| `09 08 00 00` (id `0x809`) + the one `.txd` | 70 | `.awd` 59, `.hwd` 5, `.lwd` 5, `.txd` 1 | no RenderWare section could be read from this member |
| `1d 00 00 00` | 36 | `.btv` 31, `.bgv` 5 | the first section is id `0x1d`, not the texture-dictionary id `0x16`; this is not a `.rtd` |
| `0d 08 00 00` | 24 | `.rws` 24 | … id `0x80d` … |
| `09 08 00 00` | 1 | `.awd` 1 | … id `0x809` … |
| `10 00 00 00` | 1 | `.bgd` 1 | … id `0x10` … (a clump) |

The one `.txd` is 866,176 bytes and begins `00 00 3c 54`, which is neither a
section id nor a length that fits, so it is Criterion's own container and not a
RenderWare stream [A]. A **whole-member** search of all 178 files for an
embedded texture-dictionary header — id `0x16`, a body length that fits the
member, and a RenderWare library word — found exactly **one** candidate, in a
`.bgv`, declaring a 13-byte body. Thirteen bytes cannot hold a dictionary's
`Struct`, so it is a coincidence and the honest count is **zero**.

**The assumption that would make that negative wrong** is stated in the census:
the search looks for `0x16` written little-endian at a byte boundary in a member
whose extension the disc map calls RenderWare. A dictionary compressed inside
another container, stored big-endian, or living under an extension not on that
list would be missed. The disc map records no compressed container under
`/BURNOUT`, and every EA container on the disc is `TERF`.

### 9.5 What an art page on each disc would cost

* **NFL Blitz Pro** and **Blitz: The League** — the reader is done and the
  container reader is done (`midway_pak`, `MIDWAY_PAK_FORMAT.md`), so an art
  page is *wiring*, not research: a `TextureDictionaryLane` over a pack member
  instead of a ZIP member, and the selection rule each disc's own names imply.
  What differs is the yield: The League gives up 67% of its rasters and Blitz
  Pro only 18%, so on Blitz Pro the 4-bit gap is most of the page. Neither disc
  has a writer, for §8's reason.
* **Madden NFL 06** — `rw_txd` contributes nothing. Its art page is `TERF` /
  `MMAP` / `SHPS` work, which is a reader this project already ships, and the
  Burnout demo's RenderWare would need a clump reader, an `AWD` reader and
  Criterion's `.TXD` container before it showed a single pixel.

---

## 10. What is not read

* **4-bit rasters** — 6,231 and 5,436 on the two Blitz discs, and the largest
  single gap in this format (§5). They are listed with size, depth, GS pixel
  mode, raster format and section sizes; they are not drawn. The cheapest way
  to settle it is a PCSX2 texture dump of either disc, which would give the
  candidates an answer key instead of a statistic.
* **Mip levels below zero.** The flag is read, `MIPTBP1` / `MIPTBP2` are carried
  uninterpreted, and only level 0 is decoded (§4.4).
* **`.dff` geometry.** The clump walk reads top-level section ids and library
  versions and stops (§2.1). Meshes, materials, frames, atomics and the
  `Extension` plugin chunks inside a clump are a different reader.
* **`WIFF` interiors.** `WIFF` is a big-endian RIFF — the `u32` after the tag
  plus 8 is the member on 190 of 190 and 209 of 209 [M] — and the form type is
  `WIPS`, `WOMS` or `WOM `. **No chunk inside one is read.**
* **`CPTH` camera-record field meanings.** `16 + records * 32 == the member` on
  85 of 85 and 88 of 88 [M], header word 1 takes four values (7, 1, 5, 3) and is
  reported unnamed, and a record's 32 bytes read as IEEE floats. **Which of them
  is a position and which a time is not measured and is not claimed**, so the
  lane lists a path and offers no editor.
* **The header's unnamed word at +0x3C**, and the four `misc` words at
  +0x20/+0x28 (`MIPTBP1` / `MIPTBP2`). Carried, censused (§9), never
  interpreted [A].
* **The dictionary `Struct`'s second `u16`** — the device id. Read past, never
  used.
* **Whether a dictionary is checksummed.** No field was found that varies with
  content, and nothing here has run a modified dictionary through a game, so
  that negative is only as good as the search [A].

---

## 11. Refusals

Every refusal is a `mod_editor.games.contract.Refusal` (subclass `RwTxdError`)
carrying **one sentence that names the condition**, re-raised verbatim by every
lane and asserted by the tests:

| condition | what the sentence says |
|---|---|
| shorter than a section header | a *n*-byte file is shorter than a RenderWare section header |
| larger than the reader walks | a *n*-byte member is larger than this reader walks; the largest texture dictionary on either Blitz disc is 1.1 MB |
| no section could be read | no RenderWare section could be read from this member |
| the first section is not `0x16` | the first section is id `0x…`, not the texture-dictionary id `0x16`; this is not a `.rtd` |
| no `Struct` declaring a count | the dictionary carries no `Struct` section declaring its texture count |
| an implausible texture count | this dictionary declares *n* textures, more than the 4,096 this reader walks |
| a short `TextureNative` | `TextureNative` *n* carries *k* sections; a PS2 one carries a `Struct`, two `String`s and a raster `Struct` |
| a non-PS2 platform word | `TextureNative` *n* declares platform …, not `PS2\0`; only the PlayStation 2 native raster is read here |
| missing names, missing raster `Struct` | one sentence each |
| the header is not 64 bytes | raster *n* does not begin with a 64-byte header `Struct`; this is not the PS2 raster layout |
| the header and the data section disagree | raster *n* declares *t* texel and *p* palette bytes in an *s*-byte data section; the header and the section disagree and nothing here is safe to read |
| a 4-bit raster | §5's sentence, verbatim, with both percentages |
| any other depth | a raster of *n* bits per texel is not one of the three depths measured on either Blitz disc (4, 8 and 32) |
| no `IMAGE`-mode GIF tag | raster *n*'s texel (or palette) section carries no `IMAGE`-mode GIF tag; its pixels (its CLUT) cannot be read |
| an upload too short for the size | raster *n* is *w*x*h* at *d* bits, which needs *b* bytes, and its upload carries *c* |
| a raster index the dictionary does not hold | raster *n* is not in this dictionary; it holds *k* |

---

## 12. Verifying this

```bash
PYTHONPATH=. python tests/mod_editor/test_formats_rw_txd.py    # 14 tests, synthetic only
```

The disc numbers in §3, §4 and §5 are reproduced by the two Blitz modules'
`texture_lane` inventory rows and are recorded in
`docs/product/measured/nflblitz2002_ps2/texture-dictionaries.json` and its 2003
twin. §9's numbers are reproduced by walking each disc's container with
`midway_pak` (Blitz Pro, The League), `blitz_zip` (Blitz 2002/2003) or the
ISO9660 reader (Madden 06) and handing every RenderWare-extension member to
`rw_txd.read_dictionary`; the method, the host each leg ran on and every count
are in `docs/product/measured/rw_txd/cross-disc-census.json`. **No dictionary
from any disc is committed, and the tests do not need one.**
