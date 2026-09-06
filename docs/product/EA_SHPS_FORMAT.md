# EA `SHPS` — the image bank every EA BIG-based PS2 disc keeps its art in

`MMAP` is where a Madden PS2 disc keeps its textures. `SHPS` is where the
rest of EA's PlayStation 2 output keeps them, and it is where **all of MVP
Baseball 2005's art lives**: 16,371 banks inside its 211 EA `BIG` archives —
uniforms, portraits, ballparks, field art, logos, awards, every menu widget —
plus 37 more in the EA Nation dashboard that Madden NFL 06, 08, 09 and NCAA
Football 09 all carry.

The implementation is `mod_editor/games/_formats/ea_shps.py` (pure Python,
Qt-free, standard library only — it writes PNG without Pillow), with
`tests/mod_editor/test_ea_shps.py` covering it on synthetic banks only.

**Evidence tags.** **[M]** measured by running this module against a disc this
project can reach. **[S]** sourced. **[A]** assumed — a question, not a fact.

**Retail-free.** Constants, offsets, counts and refusal sentences. No pixel,
no palette entry and no bank name from any game is reproduced here.

---

## 1. The verdict, in five sentences

1. **The container is fully decoded** [M]: header, directory and block chain,
   with zero counter-examples across 4,665 banks and 27,485 images of MVP
   Baseball 2005 and all 37 banks and 93 images of the Tiburon dashboard.
2. **Two of the four pixel codes are decoded and proved to the eye** — 8-bit
   indexed (`0x02`) and direct 32-bit RGBA (`0x05`), 20,099 of the 27,485
   images sampled — and **two are refused**, one of which is not a corner
   case: code `0x0E` is a **4×4-block codec** at 6 bytes per block — two 8-bit
   palette endpoints per block, whose layout is decoded, and 2-bit per-pixel
   selectors, whose semantics are not — and it holds every uniform, portrait,
   head texture and loading screen on the disc. §5 is the measurement, and it
   now also records the **search of a real PCSX2 dump for an answer key**:
   there is none in it, by four tests, one of them calibrated at 198 of 198 on
   pairings already known to be right.
3. **The palette is the part that is easy to get wrong twice**: a 256-entry
   CLUT is in the GS's CSM1 order and must be un-swapped, and a shorter one is
   padded past its declared length and must not be over-read. Both are settled
   by measurement, and the first is settled by eye as well.
4. **Alpha is EA's PlayStation 2 scale**, where `0x80` is opaque, not `0xFF`
   [M] — the same convention the `MMAP` decoder on the Madden side documents,
   because the two formats are different wrappers over the same hardware.
5. **An 8-bit image is written back in place.** `encode_indexed` indexes an
   RGBA image against a bank's own palette and `replace_pixels` swaps an
   image's level-0 bytes inside the bank at the same size; `EA_BIG_FORMAT.md`
   §6 is the slot writer that puts the bank back. The MVP Baseball 2005
   module's art lanes are the proof.

---

## 2. The bank, byte by byte [M]

```
+0x00  "SHPS"                also ShpS / SHPI / SHPM / SHPP / SHPX
+0x04  u32  declared size    the whole bank; it matches, 3,087 / 3,087   [M]
+0x08  u32  image count
+0x0C  4 chars directory id  "G359" on MVP, "G355" on the dashboard      [M]
+0x10  count x { 4-char tag; u32 offset from the start of the bank }

each block, at one of those offsets and chained from it:
+0x00  u8      code          what the block holds
+0x01  u24     size          THIS BLOCK only; 0 ends the chain
+0x04  u16     width
+0x06  u16     height
+0x08  u16 x4  misc          zero in every pixel block measured          [M]
+0x10  payload
```

Byte order is chosen by which reading gives a directory that fits the bank,
and reported (`ShpsBank.endian`). Every bank measured is little-endian [M];
the big-endian path exists because the same tool wrote cross-platform banks
elsewhere and is covered by a test.

### 2.1 Two things the natural reading gets wrong

1. **The block `size` covers the block, not the image** [M]. An image's
   pixels, its palette and its metadata are separate blocks laid end to end,
   each with its own 16-byte header, and only the first is reached from the
   directory. A reader that treats the directory offset as "header, then
   pixels, then the next image" finds a palette where it expects a texture.
2. **The last block of a chain declares size 0** [M]. Walking by `size` alone
   never terminates on it. The chain ends there, and that final block's bytes
   run to the next *directory* offset — which is why `ShpsBank` bounds every
   chain by the next offset in **address** order, not table order.

---

## 3. The block codes, settled by arithmetic [M]

A pixel block declares its dimensions and its byte count, so it states its own
depth: `(size - 16) / (width * height)`. Every code below was identified that
way first and confirmed by decoding second — no code table was taken on faith.

Over 27,485 images in a 4,665-bank sample of MVP Baseball 2005:

| code | what it is | images | bytes per pixel, measured |
|---|---|---:|---|
| `0x02` | 8-bit indexed | 19,697 | 1.0000 (19,431), 1.3320 (255), 1.3281 (10), 1.0323 (1) |
| `0x0E` | **refused**, see §5 | 7,996 | 0.3750, every one of them |
| `0x05` | direct 32-bit RGBA | 402 | 4.0000, every one of them |
| `0x01` | **refused**, see §5 | 321 | 16.0000 — and every one is 1×1 |

and the blocks that hang off them:

| code | what it is | blocks |
|---:|---|---:|
| `0x70` | text attachment, always last, size 0 | 28,416 |
| `0x21` | 32-bit RGBA palette | 28,014 |
| `0x69` | attachment | 22,795 |
| `0x7C` | attachment | 1,069 |
| `0x6F` | text attachment | 1 |

**The 265 `0x02` images at about four thirds of a byte per pixel carry a whole
mip chain** [M]: the levels below level 0 sum to a third of it, and four
thirds is what that looks like. Level 0 is the front of the block and is what
`decode_rgba` returns; `ShpsImage.mip_bytes` says how much followed.

**No `0x05` image carries a palette block** and no `0x02` image lacks one
[M]. `undecodable_reason` refuses either combination rather than picking one,
because a rule that holds 20,099 times is a rule until it does not.

---

## 4. The palette, which is wrong twice if it is wrong once [M]

### 4.1 A 256-entry CLUT is in CSM1 order

Within every block of 32 entries the PlayStation 2 GS swaps the second group
of 8 with the third. Undoing that is the difference between an icon and a
speckled icon.

**The proof is visual and it is symmetric** [M]: the 93 sub-images of the
Tiburon dashboard were decoded twice, once with the swap undone and once
without, into two contact sheets. With the undo, 93 clean widgets — button
glyphs, gauges, wordmarks, a photograph. Without it, the same 93 shapes
striped and speckled in the right colours. Neither sheet is committed; both
were built in a scratch directory and looked at.

The interleave applies at **exactly 256 entries and nowhere else** [M].
`deinterleave_csm1` is its own inverse, which is tested.

### 4.2 A short palette is padded, and its declared width is the authority

Roughly two thousand images on MVP carry a palette shorter than 256, and every
one of those blocks is padded out: a block that declares 122 entries carries
124, one that declares 80 carries 88, one that declares 17 carries 24 [M].

The declared width wins, and the disc proves it: across every short-palette
image measured, **the largest pixel index in the image is below the declared
width and never reaches the padding** —

| declared entries | entries in the payload | highest index used |
|---:|---:|---:|
| 122 | 124 | 121 |
| 80 | 88 | 79 |
| 61 | 64 | 60 |
| 53 | 56 | 52 |
| 27 | 28 | 26 |
| 17 | 24 | 16 |
| 16 | 24 | 15 |
| 3 | 4 | 2 |

A reader that took the entry count from the payload length would build a
palette with junk on the end. It would never show — and it would be wrong.

### 4.3 Alpha

`0x80` is fully opaque. `decode_rgba` widens 0..128 to 0..255; `raw_alpha=True`
hands back the stored byte, which is the form a **PCSX2 texture dump** carries,
so a matcher pairing a dump with a bank asks for it.

---

## 5. What is refused, and why that is not the same as empty

### `0x0E` — 7,996 images: a block codec, half decoded

**This is the single largest gap in this format, and it is not a corner
case.** Code `0x0E` holds, on MVP Baseball 2005 [M]:

The counts below come from a second pass that sampled up to 200 banks per
archive and recorded each image's first block code (20,973 images) [M].

| where | images, in that pass | share of that archive |
|---|---:|---|
| `UNIFORMS.BIG` | 158 | all of its non-stub images |
| `PORTRAIT.BIG`, `GHEAD.BIG` | 200 + 200 sampled | 100% of both |
| the 59 `LOADn.BIG` loading screens | 59 | 100% |
| `FIELDS.BIG` and the 7 ballpark-builder archives | 224 | 100% |
| `STADIUMS.BIG`, `AWARDS.BIG`, `COOPUNIS`, `COOPPLYR`, `COOPSTAD`, `COOPTEAM` | 325 | 100% |
| the 87 ballpark archives | 2,555 | 20% |
| `MODELS.BIG` | 1,249 | 29% |
| `LOGOS.BIG` | 524 | 57% |

**What it is, as measured on the retail disc (2026-09-06, one bounded
session)** [M]. An earlier pass called this "a fixed-rate compressed codec
in the executable, undecodable by rearranging bits". One of its three claims
holds and two are corrected here:

1. **The rate is exactly 6 bytes per 4×4 block** — 0.375 bytes per pixel —
   at every size, for every image; the pixel block is exactly
   `16 + w*h*3/8` bytes and **a 256-entry `0x21` palette block follows it in
   every chain** (`0x0e, 0x21, 0x69, 0x70`). Still true, and the palette
   decides what the bytes can be.
2. **The bytes are not near-uniform.** The first bytes of a uniform run
   `6c 6c 6c 18 6c 6c 6c 6c 6c 24 …`, a portrait `01 01 2c 24 01 01 23 2c
   00 00 …`, a loading screen `17 54 17 54 17 54 …`: long runs of one value
   and its neighbours. The palette is the tell: every `0x0E` image's palette
   has **246 to 252 distinct entries, all non-zero**, and the payload uses
   **254 to 256 distinct byte values**. A 4-bit image would touch 16 palette
   entries; a selector-only stream would not correlate with the palette at
   all. **These bytes are 8-bit palette indices.**
3. **The layout is two streams, not interleaved blocks.** The first `w*h/8`
   bytes are a coherent raster at width `w/2` (neighbour-colour distance
   0.3–0.45 of random, against 1.0 for the rest); the last `w*h/4` bytes are
   not a raster at any width but keep a period-4 structure. That is a
   4×4-block codec with two 8-bit endpoints and a 2-bit selector per pixel —
   DXT1's structure over a CLUT — with the two halves stored apart:

   * **Endpoint stream** (`w*h/8` bytes): one 32-bit word per two
     horizontally adjacent blocks, `[i1(x), i1(x+1), i0(x), i0(x+1)]`, in
     block-raster order. The within-word similarity matrix says so — bytes 2
     and 3 of every word form a smooth image (next word 0.32, next row 0.33
     of random), bytes 0 and 1 a rough one (0.77 / 0.90), and the two halves
     are anti-correlated (0.95–1.0), which is a dark and a light endpoint of
     one block. **Rendering every block flat in its `i0` colour gives a
     recognisable quarter-resolution portrait** (head, hair, jersey) and
     loading screen (title, panels): the block→position map is right.
   * **Selector stream** (`w*h/4` bytes): 8 bytes per pair of blocks, raster
     order (adjacent-word Hamming similarity 0.45, next row 0.65). Within a
     byte the two nibbles are unrelated (2-bit fields 0↔1 agree 61%, 2↔3
     48%, 0↔2 24% = random), and the most common selector bytes are `0x0F`,
     `0xFF`, `0x6F`, `0x5F`, `0xAF` — low nibble `1111` — the signature of
     bit-planar nibbles over a flat row.

   **What is not decoded: the per-pixel selector semantics.** Every reading
   tried leaves noise inside the blocks while the composition stays right:
   row-per-byte (LSB-first and MSB-first), one little-endian u32, two 16-bit
   planes, nibble-interleaved between the two blocks of a pair (2 pixels per
   nibble, both assignments), bit-planar nibbles (low nibble = plane 0 of a
   4-pixel row, high = plane 1) × both bit orders × all 24 orderings of the
   weights (0, ⅓, ⅔, 1), and endpoint interpolation in DXT order, linear
   order, in index space and in colour space. The total neighbour gradient
   of the portrait plateaued at 34 on every one of them, against 14.5 for
   the flat-endpoint render.

   **The 48-bit-per-block decompositions, tested against a portrait and
   rejected by the same gradient** [M] (lower is smoother; 14.5 is the
   two-stream flat-endpoint reference, raster block order):

   | decomposition | best gradient | why it is out |
   |---|---:|---|
   | (a) two RGB565 endpoints + 16 one-bit indices, per 6-byte block, both endian, both endpoint orders, both bit orders | 135.5 | worst of everything tried; and the palette block that follows every `0x0E` block would be unused |
   | (b) one RGB565 base + 16 two-bit luma steps, both endian, both bit orders, two step tables | 97.8 | random-level; same palette objection |
   | (c) two CLUT indices + 16 two-bit selectors **interleaved** per 6-byte block | 69.9 | the raster test says the two halves are separate streams, and separating them (above) gives 14.5 |
   | (d) blocks in 8×8-tile order instead of raster, applied to every reading above | worse in every case (16.4 vs 14.5 for the reference) | raster is the block order |

   Also rejected earlier, and why: 8-bit and 4-bit rasters at (w/2)·(3h/4),
   (3w/4)·(h/2) and w·(3h/8) in both nibble orders (no picture); the PS2
   `swizzle8` layout and the PCSX2 GS block permutation at every candidate
   size (their coherence gain was the endpoint stream's own structure, not a
   picture); the GS PSMCT16/PSMCT32 page swizzles over the two streams (they
   scramble the block map that raster order gets right); half-resolution
   8-bit plus a 1-bit or 4-bit plane, in either order.

#### The ground-truth attempt: a PCSX2 dump was searched for an answer key, and there is none [M]

Everything above is inference from the encoded bytes. The way to end the
argument is an **answer key** -- a picture of what one of these images decodes
to -- and a PCSX2 texture dump is exactly that, because the emulator writes out
the decoded texels of whatever the game drew. One dump of MVP Baseball 2005
now exists: three single-frame GS dumps replayed headless with texture dumping
on (1,308 files, 436 distinct textures). It was searched, by
`tools/mvp05_ps2_texture_identities.py`, with four tests. **It contains no
decoded `0x0E` texture**, and the fourth test is what makes that a measurement
rather than a failure to find one.

| # | test | what it finds | result |
|---|---|---|---:|
| 1 | the dumped filename's CLUT hash equals a `0x0E` image's palette | a palette the game uploaded to the GS exactly as the disc stores it | 1 picture |
| 2 | every colour a dumped picture uses is in a `0x0E` image's palette, **in any order** | the same, and also a palette the game re-ordered first | the same 1 |
| 3 | the payload can hold the picture: `w*h*3/8` bytes against what the dumped texels compress to | whether a candidate could be a decode of that payload at all | **0** |
| 4 | the true index image, palette inverted, has ≤ 4 distinct indices in **some** 16-texel block shape | whether two endpoints and sixteen 2-bit selectors could describe it | **0** |

Test 2 is the one with recall, and it is calibrated rather than assumed: on
**198 (dump, disc image) pairs that pair on exact pixels and whose CLUT hash
differs from the disc palette** -- the game does re-order some CLUTs before
uploading them -- the colour-set test holds **198 of 198** [M]. Across all
23,954 `0x0E` images and all 436 distinct dumped textures it finds exactly one
pairing, and 939 of the 1,308 dumped files have a size some `0x0E` image also
has, so the search was not starved of candidates.

**The one candidate, and why it is not a decode.** A 128x128 `PSMT8` texture
whose CLUT is, byte for byte, the palette of one `0x0E` image (`MODELS.BIG`,
128x128, a 6,144-byte payload -- the only image on the disc carrying that
palette). Inverting that palette on it succeeds completely: **0 of 16,384
pixels fall outside the palette**, 528 are ambiguous because their colour sits
at more than one entry, and 251 distinct indices are used. So the CLUT is
certainly that image's. The texels are not:

* **capacity.** The dumped texel image compresses to 122,072 bits. The payload
  is 6,144 bytes = **49,152 bits**. A decoder is a function of its input, so it
  cannot emit more information than its input carries, whatever the codec is.
* **block geometry.** Two endpoints and sixteen 2-bit selectors put **at most
  four** distinct indices in a block. The true index image reaches **16** and
  exceeds four in 1,010 to 1,019 of the 1,024 blocks under *every* 16-texel
  shape tried -- 4x4, 8x2, 2x8, 16x1, 1x16.

So the game uploaded that image's CLUT to the GS and PCSX2 read a texel page at
that TEX0 which was not the decoded picture. **What the dump therefore says is
where the decode is not, not what it is:** MVP's `0x0E` art does not reach the
GS as an indexed texture the emulator's dumper writes out, even though the
three frames demonstrably drew some -- one is a batter introduction card with a
portrait on it and every portrait on the disc is `0x0E`, and both batters are
in kits and every kit is `0x0E`. A different scene will not fix that; a capture
method that reaches the decoded buffer would. `docs/product/measured/mvp05_ps2/shps-0x0e-dump-pairing.json`
is the whole search with its counts.

**None of this confirms or refutes the two-stream reading above.** With no
answer key the endpoint order, the block map and the selector semantics stand
exactly where the previous session left them: the first two by the
flat-endpoint render, the third undecoded.

So the reader names the code, quotes this measurement, and still hands back
nothing: a half-right picture exported as if it were the texture is how a
modder ships a corrupted uniform. The next person starts at the selector
semantics with the block map, the endpoint order and the raster order settled.

### `0x01` — 321 images, every one of them 1×1

A 16-byte payload for a single pixel, with a two-entry palette. That proves a
block has a minimum size and nothing else: no row stride, no nibble order, no
depth. Not one `0x01` image anywhere in the sample is larger than 1×1 [M], so
there is nothing to learn it from. Refused, with that sentence.

---

## 6. Reading

```python
from mod_editor.games._formats import ea_big, ea_shps

bank = ea_shps.parse(archive.member("uniforms.ssh"), name="uniforms.ssh")
bank.image_count, bank.directory_id, bank.endian
bank.code_histogram()                  # every block of every image
bank.undecodable_reason(index)         # None, or one sentence
width, height, rgba = ea_shps.decode_rgba(bank, index)
open("out.png", "wb").write(ea_shps.encode_png(width, height, rgba))
```

`encode_png` is thirty lines of `zlib` and `binascii`: a format package does
not get to depend on Pillow, and a census that runs on a bare test machine
still needs to produce something a person can look at.

---

## 7. What was measured, in one table

| corpus | banks | images | decoded | refused |
|---|---:|---:|---:|---:|
| MVP Baseball 2005 (USA), 4,665-bank sample of 15,818 | 4,665 | 27,485 | 19,223 (70%) | 8,262 |
| NCAA Football 09 (USA), `/EACN/BUNDLE.BIG`, all of it | 37 | 93 | 93 | 0 |
| Madden NFL 09 (USA), same archive | 37 | 93 | 93 | 0 |
| Madden NFL 08 (USA), same archive | 37 | 93 | 93 | 0 |
| Madden NFL 06 (USA), same archive | 38 | 94 | 94 | 0 |

Every refusal on MVP is a `0x0E` or a `0x01` image; there is no third kind
[M]. Of the 178 archives that hold banks, **5 decode every image, 78 decode
none, and 95 are mixed** — and which side an archive falls on is decided
entirely by §5: small UI widgets and model textures are `0x02` and come out,
large photographic art is `0x0E` and does not [M]. The largest bank measured holds 198 images; the most common sizes are
64×64 (3,934), 128×128 (3,833), 16×32 (2,337) and 32×32 (2,317), the largest
decoded image is 512×512, and the largest of any kind is a 1024×256 `0x0E`
block.

---

## 8. What stays unknown

- **`0x0E`'s per-pixel selectors**, §5. The block map, the endpoint order
  and the raster order are settled; the 2-bit selector semantics are not,
  and they decide how much of an EA BIG disc's art a studio can show. The
  cheapest way to settle them is still an answer key, and §5 records what a
  three-frame PCSX2 dump of MVP Baseball 2005 did and did not supply — no
  decoded `0x0E` texel reaches the GS as an indexed texture the emulator's
  dumper writes out, so the next attempt needs a capture that reaches the
  decoded buffer rather than another scene.
- **`0x01`'s layout**, §5, and it may never be knowable from this disc.
- **The four `misc` u16s** of a pixel block. Zero in every pixel block
  measured; `0x0E` blocks carry `(0, 0, 8196, 2)` and palettes `(entries, 0,
  8192, 0)`, and 8192 is `0x2000`, which *looks* like a GS storage-mode field
  [A]. Not interpreted.
- **The `0x69` / `0x6F` / `0x70` / `0x7C` attachments.** Carried, counted,
  never parsed.
- **Whether a bank is checksummed.** No field was found that varies with
  content; nothing here has run a modified bank through a game, so that
  negative is only as good as the search.

---

## 9. Verifying this

```bash
PYTHONPATH=. python tests/mod_editor/test_ea_shps.py    # 25 tests, synthetic only
```

The disc numbers are reproduced by walking each `BIG` archive with `ea_big`,
handing every `SHPS` entry to `ea_shps.parse`, and summing `code_histogram()`,
`undecodable_reason()` and `decode_rgba()`. No bank from any disc is
committed, and the tests do not need one.
