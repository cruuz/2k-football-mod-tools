# EA `BIG` — the archive on the EA PlayStation 2 discs that are not Tiburon's

`TERF` is the container a Madden or NCAA Football PS2 disc streams from.
`BIG` is the one EA's other PS2 studios ship, and the one a Madden disc still
carries for its EA Nation dashboard. **MVP Baseball 2005 (SLUS-21135) is built
entirely out of it**: 211 archives holding 43,773 entries, no `TERF` container
anywhere on the disc and no EA `TDB` database either. A module that reads this
file reads that disc.

The implementation is `mod_editor/games/_formats/ea_big.py` (pure Python,
Qt-free, no game-specific knowledge), with
`tests/mod_editor/test_ea_big.py` covering it on synthetic archives only.

**Evidence tags, on every load-bearing claim.**
**[M]** measured — a read-only command was run against a disc this project can
reach and the result is quoted. **[S]** sourced — a citation in §9.
**[A]** assumed — inference, not verified; treat as a question.

**Retail-free.** Everything below is a constant, an offset, a count or a
statistic. No entry payload, no decoded texture and no string lifted from a
game appears here or in the code. Archive and entry *names* do appear; they
are the file system of the disc, not its content.

---

## 1. The verdict, in five sentences

1. **The archive is fully decoded** [M]. Header, entry table, payload layout
   and per-entry compression are all measured, with zero counter-examples
   across the 211 archives and 43,773 entries of the retail MVP Baseball 2005
   (USA) disc, and the same reader opens the three dashboard archives on each
   of four EA Tiburon discs unchanged.
2. **The header mixes byte orders, and that is the whole trick** [M]. The
   `u32` at `+4` is the archive's total length **little-endian**; the entry
   count, the table size and every offset and size in the table are
   **big-endian**. A reader that picks one order gets either a nonsense length
   or a nonsense count, which is exactly how this format earns its reputation.
3. **Compression is per entry, whole-stream, and the table does not mention
   it** [M]. An entry is RefPack-packed if and only if its own first two bytes
   say so. MVP packs 23,855 of its 43,773 entries; the four Tiburon discs pack
   **none** of theirs.
4. **RefPack is implemented and proved** [M]. The decoder is written from the
   published grammar and is exercised opcode by opcode in the tests; on the
   disc it unpacked **all 23,855 packed entries — 764,038,770 bytes — and
   every one of them came out at exactly the length its own header declares**,
   with no refusals.
5. **Reading is finished, and one bounded writer exists.** `refpack_compress`
   is a RefPack encoder proved by the decoder, and `rewrite_entry` replaces
   an entry inside the slot it already owns — re-packed when the disc packed
   it — rewriting the row's size word and nothing else. The measurement that
   made it possible is in §6: the slot is the entry's own size plus at most
   three bytes, and the encoder here packs every entry measured smaller than
   EA's stream did.

---

## 2. The archive, byte by byte [M]

```
+0x00  "BIGF"                                                          [M]
+0x04  u32  LITTLE-endian   total archive length, and it matches        [M]
+0x08  u32  BIG-endian      entry count                                 [M]
+0x0C  u32  BIG-endian      bytes the header and the entry table occupy [M]

+0x10  entry table, one variable-length row per entry, packed end to end:
         u32  BIG-endian    offset, from the start of the archive
         u32  BIG-endian    size
         NUL-terminated ASCII name                                      [M]

       padding to the first payload offset                              [M]
       payloads, in table order                                         [M]
```

### 2.1 Three things the natural reading gets wrong

Each of these breaks every entry of an archive, so each has a test.

1. **The length word is the only little-endian integer in the file** [M].
   Read the whole header one way and either the length is wrong or the count
   is. MVP's `/DATA/MODELS.BIG` is 122,887,425 bytes and declares 2,505
   entries: read entirely big-endian its length is 18,699,015, and read
   entirely little-endian its count is 3,372,810,240. `BigArchive` reads
   the length word **both** ways, reports which one matched
   (`size_endian`), and refuses a count outside 1..200,000 by name — "reading
   the header with the wrong byte order produces exactly this".
2. **A row's length depends on its name, so the table can only be walked
   forwards** [M]. There is no row stride and no name-length field. A reader
   that seeks to `16 + 8 * index` lands in the middle of a name.
3. **Nothing in the file declares the payload alignment** [M].
   `BigArchive.alignment()` *measures* it — the largest power of two dividing
   every non-empty offset — and reports it rather than enforcing it. On MVP it
   is 4 for 199 archives, 128 for 4, 64 for 4, 16 for 3 and 8 for 1; on the
   four Tiburon discs it is 64 for all three archives. A writer that assumed
   64 would relocate every payload in 199 archives out of 211.

### 2.2 The layout rules, checked across the whole disc [M]

| rule | evidence, MVP Baseball 2005 |
|---|---|
| the declared length equals the length ISO9660 records | 211 / 211 archives |
| table order equals offset order | 43,772 / 43,772 non-empty entries |
| no two payloads overlap, none starts inside the table, none runs past the end | 211 / 211 archives |
| every entry name is NUL-terminated inside the declared table | 43,773 / 43,773 |

Seventeen `/DATA/FRONTEND/*.BIG` archives carry **exactly one duplicated entry
name each** [M]. Lookup by name returns the first; `duplicate_names` counts
them and `layout_notes()` says so, because a caller that addresses entries by
name in those archives is addressing one of two things.

### 2.3 Files named `.BIG` that are not archives [M]

MVP has **227** files whose name ends `.BIG` and **211** archives. The other
sixteen are the audio pairs under `/DATA/AUDIO/*/`: eight are bare `SCHl`
streams (`CHANTDAT.BIG`, `PBPDAT.BIG`, …) and eight are their index files,
whose first four bytes are a count, not a magic. The reader refuses each by
name and quotes what it found instead — the name of a file is never taken as
evidence about its format.

---

## 3. RefPack, the per-entry codec [M]

### 3.1 The header

```
+0x00  u8   flags     bit 0x01: sizes are 4 bytes wide, else 3
                      bit 0x80: a compressed size precedes the decompressed one
                      bits 0x3E: the family marker, 0x10
+0x01  u8   0xFB
[+0x02  u24/u32 BE compressed size, only when 0x80 is set]
 +...   u24/u32 BE decompressed size
```

Every packed entry on every disc measured uses three-byte sizes with no
compressed-size field — the `10 FB` shape [M]. The other two combinations are
implemented and tested because the flag bits are the format's, not the disc's.

### 3.2 The opcode grammar

After the header the stream is opcodes, each carrying a count of *literal*
bytes that follow it and, in three of the four shapes, a back-reference into
the output produced so far [S].

| first byte | bytes | literals | offset | length |
|---|---|---|---|---|
| `0x00-0x7F` | 2 | 0-3 | ≤ 1,024 | 3-10 |
| `0x80-0xBF` | 3 | 0-3 | ≤ 16,384 | 4-67 |
| `0xC0-0xDF` | 4 | 0-3 | ≤ 131,072 | 5-1,028 |
| `0xE0-0xFB` | 1 | 4-112, in fours | — | — |
| `0xFC-0xFF` | 1 | 0-3, then the stream ends | — | — |

Two details a naive port gets wrong: the literals of a copy opcode come from
the bytes **after** the opcode and are emitted **before** the copy; and a copy
whose length exceeds its offset is a *repeat* with period `offset`, not a
slice — `refpack_decompress` does that as one multiplication and has a test
that would fail on a slice copy.

### 3.3 What was measured

| measure | MVP Baseball 2005 (USA) |
|---|---|
| entries that are RefPack streams | 23,855 of 43,773 [M] |
| entries whose unpacked length equalled their own declared length | **23,855 of 23,855** [M] |
| entries this decoder refused | 0 [M] |
| bytes produced by that pass | 764,038,770, in 25.8 s [M] |
| archives with a packed entry | 194 of 211 [M] |
| RefPack entries on the four Tiburon discs | 0 of 344 [M] |

A **bounded** decode is the census tool: `member(index, max_output=32)` reads
only the front of the stream and stops as soon as 32 bytes exist, so a 30 MB
texture bank is classified for the price of a kilobyte. Running out of input
is an error in a full decode and a normal stop in a bounded one; the two paths
are separate and both are tested.

**The encoder** (`refpack_compress`, 2026-09-06) is a hash-chain LZ77 over
three-byte prefixes, most recent first, one-step lazy, emitting every opcode
shape by the decoder's own table. Proved by round trip through
`refpack_decompress` on synthetic data and on the disc. Its output against
EA's, measured on MVP Baseball 2005 [M]:

| chain depth | database tables (18) | ROOKIE tables (20) | texture banks (40) |
|---|---|---|---|
| 48 | 6 of 18 **larger** than EA's stream, by 9 to 3,810 bytes | 5 of 20 larger, by 1 to 14 | all smaller |
| **256 (default)** | **all 18 smaller**, by 10 (`contact.csv`) to 8,687 (`attrib.dat`) | all smaller | all smaller |
| 1,024 | all smaller, `attrib.dat` by 13,428 | — | — |

At 256 the 751 KB `attrib.dat` packs in about 15 s in pure Python; 1,024
buys 4.7 KB more margin for twice the time and is not the default.

---

## 4. Entry formats [M]

Classification is delegated to `ea_terf.identify_member`, the same magic table
the `TERF` reader uses, so a head is never named one thing on one disc and
another elsewhere. `BigArchive.entry_format` adds the two answers only this
format needs: `empty` for a zero-length entry, and `undecodable` for a RefPack
stream the decoder could not follow — which is a different answer from
`unclassified` and must not render the same.

MVP Baseball 2005, every entry at every depth [M]:

| format | entries |
|---|---:|
| `SHPS` (image bank) | 16,371 |
| unclassified | 13,933 |
| `SCHl` (audio stream) | 9,123 |
| `ELF` (IOP object) | 4,077 |
| `TEXT` | 2,044 |
| `BIGF` (a nested archive) | 643 |
| `FNTS` (font) | 2 |
| `BNKl` (sound bank) | 2 |
| empty | 1 |

The 13,933 unclassified are the animation and model side of the disc: 3,499
`.orl` object-relocation files, 641 `.apt` and 641 `.const` dashboard screens,
261 `.ifo` and the rest. They are counted and left alone.

**Nested archives are opened in place.** A stored nested archive reuses the
outer archive's ranged reader with a shifted base, so nothing is copied; a
packed one is decompressed first. MVP's `/DATA/APTANIMS/EASOAPT.BIG` holds 641
nested archives with 2,423 entries between them [M]; each Tiburon disc's
`/EACN/BUNDLE.BIG` holds 70 [M].

---

## 5. Reading

```python
from mod_editor.games._formats import ea_big

# From bytes, an mmap, or a ranged reader -- anything that answers
# read(offset, size).  The last is how a disc is read: an archive 122 MB
# into an ISO opens without the ISO being copied anywhere.
archive = ea_big.parse_big(read, size=entry.length, base=lba * 2048,
                           name="/DATA/MODELS.BIG")

archive.entry_count                 # what the header declares
archive.size_endian                 # which reading of +4 matched the file
archive.alignment()                 # measured, never assumed
archive.layout_notes()              # empty for an ordinary archive
archive.member("uniforms.ssh")      # bytes, RefPack-decoded if packed
archive.entry_format(0)             # after decompression, always
archive.nested(index)               # another BigArchive, no copy
archive.summary()                   # counts and sizes, no payload
```

`tools/` has no inspector for this format yet; the census that produced every
number in this document was a scratch script that used nothing but the calls
above.

---

## 6. Writing: the bounded writer, and the measurement that bounds it

A `BIG` archive has no chunk chain to rebuild and no checksum field, so a
writer looks easy. The measurement says otherwise, and it is one number.

**An entry's slot is its own size plus at most three bytes** [M]. Across all
43,772 non-empty entries of MVP Baseball 2005:

| slack between an entry's end and the next payload | entries |
|---|---:|
| 0 bytes | 25,946 |
| 1 byte | 6,441 |
| 2 bytes | 5,536 |
| 3 bytes | 5,847 |
| 60 bytes | 1 |
| 64 bytes or more | 1 |

So the bounded shape — the one that changes two byte ranges and moves
nothing — is: **keep the entry's name, write no more bytes than it already
had, rewrite the four-byte size word in its table row, and copy the payload
into the space it already owns.** `plan_entry_rewrite` computes exactly that
and returns `fits_slot`, `slot_bytes` and the blockers.

Anything larger relocates every payload after it and rewrites every table row
from that point on. So does changing a name, because a row's length is its
name's length. Neither is implemented.

**`rewrite_entry` does exactly the bounded shape** (2026-09-06): the plain
payload is re-packed with `refpack_compress` when the disc packed the entry,
the stored bytes must fit `slot_bytes`, the row's size word is rewritten,
the new bytes go at the entry's own offset and the rest of the old stored
size is zeroed so no old byte lingers, and the two ranges are returned with
the new archive. It refuses by name — with the slot and the packed size —
when the result does not fit. The MVP Baseball 2005 module's table, art and
bank writers all end in it, and its independent verifiers re-read the
archive out of the new image and compare every other entry byte for byte.

What stays unmeasured: **no archive rebuilt by this project has been loaded
by any game**, so whether the header's length word, the table's offsets or
something outside the archive is also checked is unknown. Every plan and
receipt says so.

## 7. What remains unknown

- **The padding between the table and the first payload.** Zero to one
  alignment unit; not interpreted, and not assumed to be zero.
- **Whether anything checksums an archive.** No field in the header varies
  with content in a way this reader could find, and there is no per-entry
  digest. **The negative is only as good as that search** — nothing here has
  run a modified archive through a game.
- **`BIG4` and the RefPack-wrapped archive** (`C0 FB`). Both are recognised by
  magic and refused by name. Neither appears on any disc in reach, so neither
  reading is guessed at [M].
- **The sixteen `.BIG`-named audio index files** on MVP. Their first four
  bytes are a count and their rows are fixed-width [A]; nothing here parses
  them.
- **The seventeen duplicated entry names.** Which of the two the game loads is
  not established.

---

## 8. Cross-title: one reader, five discs [M]

| disc | archives | entries, all depths | nested archives | RefPack | `SHPS` banks | alignment |
|---|---:|---:|---:|---:|---:|---|
| MVP Baseball 2005 (USA), SLUS-21135 | 211 | 46,196 | 643 | 23,855 | 16,371 | 4 / 8 / 16 / 64 / 128 |
| Madden NFL 09 (USA) | 3 | 344 | 70 | 0 | 37 | 64 |
| NCAA Football 09 (USA) | 3 | 344 | 70 | 0 | 37 | 64 |
| Madden NFL 08 (USA) | 3 | 344 | 70 | 0 | 37 | 64 |
| Madden NFL 06 (USA) | 3 | 343 | 72 | 0 | 38 | 64 |

MVP's 46,196 is every entry at every depth; its 211 archives declare 43,773
between them and their 643 nested archives declare the other 2,423.

The four Tiburon discs carry the same three archives under `/EACN` — the EA
Nation dashboard, its localisation and its IOP modules — and everything else
on those discs is `TERF`. The two counts agree with the owner's independent
disc mapper on all five discs.

---

## 9. Sources

- **[S]** RefPack's opcode grammar and header flags are public and have been
  documented in several independent reimplementations since the early 2000s;
  the decoder here is written from the grammar rather than ported from any of
  them.
- **[S]** The `BIGF` header's mixed byte order is recorded in the owner's
  `tools/owner/ea_disc_map.py` disc mapper, which was read before this module
  was written and is not copied into it.
- **[M]** Every count in this document came from running `ea_big` itself —
  locally against four ISOs this box holds, and over SSH against the MVP
  Baseball 2005 ISO on the test rig, read-only, one process.

---

## 10. Verifying this

```bash
PYTHONPATH=. python tests/mod_editor/test_ea_big.py     # 34 tests, synthetic only
```

The disc numbers are reproduced by opening each `.BIG`-named file on a disc
with `parse_big` and summing `summary()`, `format_histogram(follow_nested=True)`
and `compressed_count()`. No fixture from any disc is committed, and the tests
do not need one.
