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
   images sampled — and **two are refused by name with the measurement that
   failed to identify them**, which is the whole of §5.
3. **The palette is the part that is easy to get wrong twice**: a 256-entry
   CLUT is in the GS's CSM1 order and must be un-swapped, and a shorter one is
   padded past its declared length and must not be over-read. Both are settled
   by measurement, and the first is settled by eye as well.
4. **Alpha is EA's PlayStation 2 scale**, where `0x80` is opaque, not `0xFF`
   [M] — the same convention the `MMAP` decoder on the Madden side documents,
   because the two formats are different wrappers over the same hardware.
5. **Nothing here writes.** An `SHPS` bank sits inside a `BIG` entry, and
   `EA_BIG_FORMAT.md` §6 says why that entry cannot be replaced yet; an
   encoder written before then would have nowhere to put its output.

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

### `0x0E` — 7,996 images, exactly three bits per pixel

This is the crowd-and-wall art of the 87 ballpark archives; it is one bank
per stadium, and every image in it is code `0x0E` with a 256-entry palette
attached. Its arithmetic is exactly **0.375 bytes per pixel** across all 7,996
measured — a 256×256 image in 24,576 bytes, a 128×64 in 3,072 — with no
exception at any size.

Three bits per pixel is not a depth. The two readings that produce the right
*number* of bytes were both tried and both looked at [M]:

- 8-bit indexed at three eighths of the declared height;
- 4-bit indexed at three quarters of it, in both nibble orders.

All three sheets come out with plausible colours — blue crowds, green grass,
brown dirt, so the palette is certainly right — and no coherent image. So the
pixel layout is **not known**. The reader names the code, quotes the 0.375,
says which readings were tried, and hands back nothing. A half-right picture
exported as if it were the texture is how a modder ships a corrupted stadium.

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
| MVP Baseball 2005 (USA), 4,665-bank sample of 15,818 | 4,665 | 27,485 | 19,223 | 8,262 |
| NCAA Football 09 (USA), `/EACN/BUNDLE.BIG`, all of it | 37 | 93 | 93 | 0 |
| Madden NFL 09 (USA), same archive | 37 | 93 | 93 | 0 |
| Madden NFL 08 (USA), same archive | 37 | 93 | 93 | 0 |
| Madden NFL 06 (USA), same archive | 38 | 94 | 94 | 0 |

Every refusal on MVP is a `0x0E` or a `0x01` image; there is no third kind
[M]. The largest bank measured holds 198 images; the most common sizes are
64×64 (3,934), 128×128 (3,833), 16×32 (2,337) and 32×32 (2,317), the largest
decoded image is 512×512, and the largest of any kind is a 1024×256 `0x0E`
block.

---

## 8. What stays unknown

- **`0x0E`'s pixel layout**, §5. The single biggest gap in this format.
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
