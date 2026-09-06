# EA `TERF` — the Madden / NCAA Football PS2 on-disc container

Every large `/DATA/*.DAT` on an EA Tiburon PlayStation 2 disc is a `TERF`
container. Madden NFL 09's rosters, team databases, uniform art, stadium and
field geometry, player and coach faces, fonts, playbooks and speech banks all
arrive through it. This document is the format as measured, the codec verdict,
and what RC87's lanes can build on.

The implementation is `mod_editor/games/_formats/ea_terf.py` (pure Python,
Qt-free, no game-specific knowledge), with `tools/ea_terf_inspect.py` to point
it at bytes and `tests/mod_editor/test_ea_terf.py` covering it on synthetic
containers only.

**Evidence tags, on every load-bearing claim.**
**[M]** measured — a read-only command was run against a disc this box holds
and the result is quoted. **[S]** sourced — a citation in §10.
**[A]** assumed — inference, not verified; treat as a question.

**Retail-free.** Everything below is a constant, an offset, a count or a
statistic. No member payload, no decoded texture and no string lifted from a
game appears here or in the code.

---

## 1. The verdict, in five sentences

1. **The container is fully decoded** [M]. Header, chunk chain, directory,
   codec table and member layout are all measured, with zero counter-examples
   across the 107 containers and 47,769 members of the retail Madden NFL 09
   (USA) disc, and the same reader opens six other EA PS2 discs unchanged.
2. **`COMP` is a parallel directory, not a compressed blob** [M]. It is the
   same shape as `DIR1` — one `(u32, u32)` row per member — carrying a codec id
   and a decompressed size. **Compression is per member, whole-stream: no block
   table, no chunking, no per-block header** [M][S].
3. **The codec is decoded and implemented.** Codec 5 (`LZH1`, aluigi's
   `ea_madden`) is deflate's symbol grammar with MSB-first bit packing and code
   lengths stored as raw 4-bit values — no code-length-code layer, and **not**
   RefPack [S]. Codec 1 (`RLE1`) is a one-byte-escape run encoder [S]. Codec 0
   is stored.
4. **It is verified against an independent implementation**: 3,309 real
   compressed members of the Madden 09 disc were decoded by this module and by
   the owner's `nfl-online-revival/tools/lzh1.py`, and **all 3,309 are
   byte-identical**, each equal to the length its `COMP` row declares [M].
5. **Reading is finished; writing is finished except for one codec.** There is
   no `LZH1` encoder here or anywhere public [S], so `build_terf` refuses to
   write one by name. Storing is the way out and it has retail precedent (§5.4).

---

## 2. The container, byte by byte [M]

Everything is a chunk: a 4-character ASCII tag and a `u32` **total** size that
includes the 8-byte header. Walk the file by adding that size. All integers are
little-endian on PS2.

```
TERF chunk                     size = headerSize
  +0x00  "TERF"
  +0x04  u32  headerSize        = max(16, alignment)                    [M]
  +0x08  u8 2, u8 2, u8 0, u8 5  version word, meaning unknown          [M]
  +0x0C  u16  alignment          member-data alignment: 4, 16, 64, 2048 [M]
  +0x0E  u16  memberCount
  ...    zero padding to headerSize

[HSH1 chunk]                   optional; exactly one container per disc  [M]

DIR1 chunk                     size = roundup(8 + 8 * memberCount, alignment)
  +0x00  "DIR1"
  +0x04  u32  chunkSize
  +0x08  memberCount x { u32 offset; u32 storedSize }
  ...    zero padding

[COMP chunk]                   same size formula; present only when a member
  +0x00  "COMP"                 is compressed                            [M]
  +0x04  u32  chunkSize
  +0x08  memberCount x { u32 codecId; u32 decompressedSize }
  ...    zero padding

DATA chunk                     size = fileLength - dataChunkOffset
  +0x00  "DATA"
  +0x04  u32  chunkSize
  ...    member payloads
```

Three chunk chains exist and no others, across all seven discs measured [M]:
`TERF -> DIR1 -> DATA`, `TERF -> DIR1 -> COMP -> DATA`, and exactly one
`TERF -> HSH1 -> DIR1 -> DATA` per disc (Madden 09: `UIS_FONT.DAT`). A reader
must therefore **walk the chain by tag**; one that seeks to `headerSize` and
demands `DIR1` there refuses that container.

### 2.1 Three things the natural reading gets wrong

Each of these corrupts every member of a container, so each has a test.

1. **Member offsets are relative to the offset of the `DATA` *tag*, not to the
   start of its payload** [M]. The natural reading is off by the 8-byte chunk
   header. (Independently recorded by the owner's census, and by WATTO's
   original 2005 write-up [S].)
2. **The alignment is read from the file, never assumed** [M]. Madden 09 uses
   64 for 49 containers, 4 for 46, 2048 for 5 and 16 for 1. Earlier notes in
   this project recorded "0x80-aligned" and treated the `0x0800` seen in
   `BGM.DAT` / `SOUNDDAT.DAT` as an *audio flag*; both are wrong. `0x0800` is
   `alignment = 2048` — DVD-sector alignment for streamed audio — and 64-byte
   alignment produces `0x80`-looking offsets often enough to mislead. The
   community name for this field is `filePad` [S].
3. **An empty member still occupies one alignment unit** [M]. The next offset
   is `roundup(offset + max(storedSize, 1), alignment)`. 323 of Madden 09's
   members are empty, 270 of them consecutive in `UNIFORMS.DAT`; a writer that
   packs them at zero width relocates everything after them. Corroborated
   independently: "storedSize == 0 means one filePad unit of nulls" [S].

### 2.2 The layout rules a writer must reproduce [M]

Checked across every Madden 09 container that fits in memory — **zero
violations**:

| rule | evidence |
|---|---|
| `headerSize == max(16, alignment)` | 107 / 107 |
| `DIR1` and `COMP` are each `roundup(8 + 8*count, alignment)` | 107 / 107 |
| `DATA` chunk size ends exactly at end-of-file | 107 / 107 |
| members follow in table order at aligned offsets, empties counted | 47,769 / 47,769 |
| every inter-member gap is zero-filled | 24,800 gaps |
| the tail after the last member is zero-filled | 100 / 100 files scanned |
| the file length is a whole number of alignment units | 107 / 107 |

`TerfContainer.layout_violations()` is exactly this list, and `build_terf`
reproduces it; a test asserts the writer and the reader agree at every
alignment.

---

## 3. `COMP`: how compressed members are stored [M]

`COMP` is a second directory with the same geometry as `DIR1`. For member *i*:

- `DIR1[i] = (offset, storedSize)` — where the member sits and **how many
  bytes it occupies on the disc** (compressed, if it is);
- `COMP[i] = (codecId, decompressedSize)` — **how to decode it and how long the
  result must be**.

A container with no `COMP` chunk is one where every member is stored.

Each member is an **independent, whole compressed stream**. There is no block
table, no chunking and no per-block header — confirmed by measurement (3,309
members decode as single streams to exactly their declared size) [M] and by
aluigi's QuickBMS script, which decodes each member with one `clog` call from
its `DIR1` offset and size [S].

### 3.1 Codec ids

| id | name | Madden 09 | this module |
|---:|---|---:|---|
| 0 | `NONE` (stored) | 43,500 members | reads, writes |
| 1 | `RLE1` (aluigi: `TDCB_silence`) | 0 | reads, writes |
| 2 | `HUFF` | 0 | refused by name |
| 3 | `LZM1` | 0 | refused by name |
| 4 | `IPU1` | 0 | refused by name |
| 5 | `LZH1` (aluigi: `ea_madden`) | 4,269 members | reads; **cannot write** |

Ids and names come from the `register_codec` run in the EA Tiburon PS2
executables [S]. **Madden 09 uses only 0 and 5** [M]. NCAA Football 09 is the
only disc on this box that uses 1 — 433 members [M]. Ids 2, 3 and 4 are
registered by the engine and used by no member of any of the seven discs
measured here [M]; a member carrying one is refused by name, because "this
reader cannot open it" and "there is nothing there" must not render the same.

*A third-party report of a codec 3 member in NASCAR Thunder 2004 PS2 exists and
nobody has implemented it* [S]; nothing on our discs needs it.

### 3.2 Codec 5, `LZH1` — the grammar

Deflate's symbol alphabet, MSB-first bit packing, and a code-length table
stored as raw 4-bit values with no code-length-code layer:

```
loop:
  1 bit      1 => end of stream (32 further bits follow and are ignored)
             0 => a block follows
  285 x 4 bits   code lengths, literal/length alphabet (symbols 0..284)
   30 x 4 bits   code lengths, distance alphabet (symbols 0..29)
  symbols until 256 (end of block), then loop
```

Length and distance ladders are deflate's, with one difference: the length
alphabet stops at 285 symbols rather than 286, so the last base is 227 and
deflate's 258 never appears. This is what the module implements.

Two independent derivations agree on all of it. The owner reversed it out of
Madden NFL 2004's codec descriptor 5 and named it `LZH1` after the descriptor's
own four characters [S]. Separately, aluigi's `ea_madden` is a lifted x86 blob
with no readable source, but its **static tables** were extracted and matched
against RFC 1951: the 30-entry distance base and extra-bits tables match
exactly, the length tables match 28 of 29 with the final entry 228 rather than
258, and RFC 1951's code-length permutation is **absent** — which is the same
statement as "no code-length-code layer" [S]. It is **not** RefPack: there is
no `0xFB` magic and no `10FB`/`11FB`/`90FB` header anywhere in these members [M].

### 3.3 Codec 1, `RLE1` — the grammar

A literal byte, or `0x21 <value> <count>` for a run. The escape is ASCII `!`,
read out of NCAA Football 2004's decoder rather than guessed [S]. There is no
"literal `0x21`" escape, so an encoder must emit a lone `!` as a run of one,
and a stream ending after a `0x21` is truncated rather than short.

### 3.4 The verification [M]

3,309 compressed members of the retail Madden 09 disc — every `LZH1` member of
`FIELDART`, `GAMEDATA`, `COACHES`, `COACFACE`, `UNIFORMS`, `PLADATA`,
`STADATA`, `ANIMDATA`, `FANDATA`, `LOADDATA`, `CAFEOTRP` and seven `UIS_*`
containers — were decoded twice: once by this module, once by the owner's
`nfl-online-revival/tools/lzh1.py`. **3,309 identical, 0 differing**, and every
one equal to the size its `COMP` row declares. A decode of any other length is
a refusal here, never a short result.

---

## 4. Member formats [M]

**A packed member's stored magic tells you nothing about its format.** 39 of
Madden 09's 107 containers change classification between their stored and their
decompressed bytes, so `identify_member` is only ever applied after
decompression. It names `MMAP`, `SMF\0`, `DMF\0`, `TDB` (`DB` + a plausible
table count), `TERF` (nested), `QL01`, `HSH1`, `BIGF`/`BIG4`, `SCHl`, `MPCh`,
`BNKl`, `FNTS`, `SKL1` (and its byte-reversed `1LKS` spelling), `SEVT`, `EAGL`,
the `SHPS` image-bank family, `ELF`, printable `TEXT`, and `empty`; an
unrecognised head returns `None`, which is an answer and not a failure.

Over all 47,769 members of the retail disc:

| format | members | where |
|---|---:|---|
| `TEXT` | 14,748 | the story generator's templates |
| `SCHl` | 11,389 | EA audio: the speech banks, `BGM`, `SOUNDDAT` |
| `MMAP` | 11,338 | **textures**, across 45 containers |
| unclassified | 6,676 | UI screen definitions and animation blobs |
| `SMF\0` | 1,447 | static geometry: fields, stadiums |
| `empty` | 650 | padding slots |
| `TERF` | 507 | nested containers |
| `TDB` | 354 | `DB_TEAMS` 235, `GAMEDATA` 104, `TEMPLATE` 15 |
| `DMF\0` | 324 | animated models |
| `BNKl` | 301 | sound banks |
| `FNTS` / `MPCh` / `SEVT` / `SKL1` / `ELF` | 14 / 9 / 3 / 8 / 1 | |

### 4.1 The containers RC87's lanes want

| container | bytes | chunk | members | codec mix | member formats |
|---|---:|---|---:|---|---|
| `UNIFORMS.DAT` | 55,743,360 | `COMP` | 725 | 455 LZH1 / 270 stored | 455 `MMAP`, 270 empty |
| `STADIUMS.DAT` | 68,809,408 | `COMP` | 1,355 | 666 / 689 | 651 `SMF`, 434 `MMAP`, 270 empty |
| `FIELDART.DAT` | 7,380,032 | `COMP` | 715 | 715 / 0 | 642 `SMF`, 73 `MMAP` |
| `DB_TEAMS.DAT` | 2,585,792 | `DATA` | 235 | 0 / 235 | 235 `TDB` |
| `TEMPLATE.DAT` | 2,160,320 | `DATA` | 18 | 0 / 18 | 15 `TDB`, 3 empty |
| `GAMEDATA.DAT` | 4,422,400 | `COMP` | 115 | 104 / 11 | 104 `TDB`, 8 `MMAP`, 1 `TEXT`, 1 empty, 1 other |
| `UIS_PLYR.DAT` | 13,308,032 | `DATA` | 3,286 | 0 / 3,286 | 3,286 `MMAP` |
| `PLYRFACE.DAT` | 12,077,056 | `DATA` | 532 | 0 / 532 | 532 `MMAP` |
| `COACFACE.DAT` | 8,316,928 | `COMP` | 711 | 711 / 0 | 711 `MMAP` |
| `TATTOOS.DAT` | 226,496 | `DATA` | 82 | 0 / 82 | 82 `MMAP` |
| `UIS_FONT.DAT` | 147,648 | `DATA` | 10 | 0 / 10 | 10 `FNTS` (the one `HSH1` chain) |

The full 107-row table, and the totals above, are in the read-only inventory in
the scratchpad (`terf-work/inventory-m09-vanilla.md`); it is not committed
because it is a measurement of a retail disc, and the counts here are its
summary.

**Correction owed to `GAME_STUDIO_SHELL_PLAN.md` §5.** That plan's uniform-art
lane says "FSH inside BIG decoded to PNG". Madden 09's uniform textures are
**`MMAP` members inside `TERF`**, not FSH inside BIG [M]. The disc's only
`BIGF` archives are the three EA Nation dashboard files under `/EACN/`, which
hold the online UI, not kit art [M via the owner's census, re-confirmed here].

### 4.2 The `MMAP` header, as far as it is measured

Measured on 5,192 stored `MMAP` members of `PLYRFACE`, `UIS_PLYR`, `TATTOOS`,
`UIS_MCFL` and `UIS_LOAD`:

| offset | field | evidence |
|---|---|---|
| `+0x00` | `"MMAP"` | 5,192 / 5,192 [M] |
| `+0x04` | `u32` version | **2** in 4,004 and **1** in 1,188 (all of `UIS_MCFL`) [M] |
| `+0x08` | bytes `00 01 02 03` | 5,192 / 5,192 [M] |
| `+0x0C` | `u16` 1 / `u16` 1 or 2 | [M] |
| `+0x10` | `u32` 0 or 1 | [M] |
| `+0x14` | `u32` a payload size | a size; its exact scope is **not** established — it sits 12, 28 or 98 bytes short of the member for different container families [M] |
| `+0x18` | `u32` header size | **40** in 5,192 / 5,192 [M] |
| `+0x1C`, `+0x20`, `+0x24` | three ascending `u32` sizes | [M] |
| `+0x28`, `+0x2A` | `u16` width, `u16` height | nine distinct widths across the sample — 64, 96, 112, 128, 256, 320, 480, 512 [M] |

`parse_mmap_header` returns those fields and hands back everything from the end
of the declared header to `+0x40` verbatim as `descriptor`.

**Pixel format, palette presence and mip count are not determined**, and are
deliberately not guessed. What is known: the two `u16` at `+0x2C`/`+0x2E` take
six distinct value pairs across the sample, and the `u32` at `+0x30` equals
`width * height` exactly for the 128×128 and 64×64 face textures — consistent
with 8-bit indexed pixels, and not proof of it [A]. A census note hypothesising
"512 bytes of 4bpp plus a 64-byte palette" for a 32×32 member was laid out by
hand on three members and does not survive the wider sample [M]. Decoding
pixels is the uniform-art lane's job; this parser does not touch them.

---

## 5. Writing

### 5.1 `build_terf(members, chunk="DATA"|"COMP", codecs=None, alignment=64)`

Builds a container from plain payloads, reproducing every layout rule in §2.2.
It compresses the members itself, and **decompresses every member it writes and
compares before returning** — a container it cannot read back is never handed
out. A `DATA` container refuses a `codecs` argument rather than dropping it.

### 5.2 `rewrite_member(container, index, payload, *, codec=CODEC_STORED)`

Replaces one member and keeps every other member byte-identical, updating the
directory, the codec table and the `DATA` size. When the new payload occupies
the same aligned slot as the old one, **nothing after it moves and the file
length does not change**; tests assert both the same-slot and the growing case.
It refuses an index that does not exist, and refuses any container that already
departs from the layout rules — rewriting one would move bytes the function
cannot account for. A plain `DATA` container takes `CODEC_STORED` only: it has
nowhere to record a codec, so a compressed member there would be handed back
still packed.

`plan_member_rewrite(container, index, payload)` prices a replacement before
anything is built. **The smallest encoding wins and a tie goes to stored**;
both shapes are ones the shipped game already loads, so the choice is about
space rather than risk. The plan says whether the replacement stays inside the
aligned slot the member already owns — in which case no other member moves —
and whether the container grows at all, which is what a caller under a fixed
allocation needs before it writes.

### 5.3 `lzh1_compress(payload, *, budget=None, verify=True)` — the encoder [M]

There was no `LZH1` encoder here, in the owner's repository, or anywhere
public; there is one now. It is written from the grammar in §3.2 rather than
lifted from anything, and the claim is one-directional: `lzh1_decompress(
lzh1_compress(x)) == x`, never `lzh1_compress(decompress(m)) == m` for a
shipped member — our parse and our code lengths are not EA's, and the sizes
below show it.

Three constraints separate it from a deflate encoder, and each one is a way to
emit a stream that decodes to *plausible* bytes rather than to an error:

* **the longest match is 227, not deflate's 258** — symbol 284 is the top of
  the 285-symbol alphabet and carries no extra bits, so a 258-byte match from
  the parse is **split** (227 + 31, and 228 as 225 + 3, so both halves stay
  legal) rather than truncated;
* **the longest distance is 32,767, not 32,768** — the window is indexed
  `(write − distance) & 0x7FFF`, so 32,768 aliases to the write pointer;
* **no match may reach before the start of the stream** — the window's initial
  contents are never written, and a distance past the bytes emitted so far
  decodes as zeros in one reader and as stale window bytes in another.

Two rules of the writer's own: every code emitted is **complete** (Kraft sum
exactly 1), and the distance table is never all-zero — whether this codec's
decode tree tolerates an incomplete code is not established from the binary and
this makes the question moot for the price of two four-bit fields. A
single-symbol alphabet gets a second, never-emitted symbol at length 1.

The **parse** is zlib's greedy-plus-lazy hash-chain match search, read back out
of a raw deflate stream and re-expressed under those constraints; the entropy
stage is this module's own — one block per member, an optimal length-limited
Huffman code, the flat 285 + 30 four-bit table the format demands. A
pure-Python match search would be the same algorithm two orders of magnitude
slower over a 361 MB corpus.

**The proof, over every `LZH1` member of the three art containers** [M]:

| container | members | EA's bytes | ours | ratio | worst member | ≤ 1.00× |
|---|---:|---:|---:|---:|---:|---:|
| `UNIFORMS.DAT` | 455 | 55,700,494 | 55,889,725 | 1.0034 | 1.0681 | 172 |
| `STADIUMS.DAT` | 666 | 60,157,259 | 61,309,008 | 1.0191 | 1.0991 | 386 |
| `FIELDART.DAT` | 715 | 7,346,476 | 6,969,682 | 0.9487 | 1.9624 | 643 |
| **total** | **1,836** | **123,204,229** | **124,168,415** | **1.0078** | 1.9624 | **1,201 (65%)** |

361,441,396 raw bytes. **Every one of the 1,836 re-encoded members decoded back
to its own input byte for byte, under this module's decoder and under the
owner's independent `tools/lzh1.py`, in both the bounded read a container
performs and the read that terminates on the end-of-stream marker** — 7,344
successful decodes, zero failures. Aggregate size is **parity** with EA's
encoder rather than the 0.96× the owner's design predicted on playbook data;
the median member is 0.9896×, and the outliers in both directions are small
members where the 158-byte flat code-length table dominates. The 15-bit code
ceiling is binding: 210 members need a 15-bit code, so the length limiter is
load-bearing rather than insurance.

`budget=` is a hard ceiling that **raises** rather than returning a best-effort
stream, and `verify=True` (the default) decompresses the result twice — bounded
and to the marker — before returning it.

### 5.4 Storing, and its retail precedent [M]

**A `COMP` container also accepts stored members.** Madden 09 ships 270 of
`UNIFORMS.DAT`'s 725 members and 689 of `STADIUMS.DAT`'s 1,355 as codec 0
*inside a `COMP` container*, so a stored member there is a shape the shipped
game already loads. That is what `plan_member_rewrite` falls back to when a
payload does not compress, and it costs space: `UNIFORMS` member 0 is 117,926
stored against 356,820 unpacked. `RLE1` is available as a middle option for
run-heavy payloads, but Madden 09 uses **no** codec-1 member, so writing one
there rests on the engine's registration of codec 1 rather than on retail
precedent from that disc [A].

---

## 6. What remains unknown

**The version word `02 02 00 05`** [A]. Identical in all 591 containers across
seven discs [M]. One reading in circulation is `u8 major, u8 minor, u8, u8
intSize=5` [S]; nothing measured here distinguishes it from any other reading,
so the module checks it and does not interpret it.

**Whether any checksum covers a container — and how weak that negative is.**
No field in the `TERF` header, the chunk headers, `DIR1` or `COMP` varies with
content in any way this module could find: every header field measured is
either a constant, a count, an offset or a size, and all of them are accounted
for by the layout rules, which hold with zero residue across 47,769 members
[M]. **That is the whole of the search, and it is not proof.** A checksum could
sit in a member, in `HSH1`, in the executable's own table, or in the
`GAME.QKL` / `FE.QKL` preload copies. Two things must be said plainly:

- The honest test — modify a container, boot the game, see whether it loads —
  **has not been run**, and cannot be run from this box: it needs the disc
  rebuilt and PCSX2 on the rig.
- There is strong *circumstantial* evidence that no container-level checksum is
  enforced: the community's Madden 09 Deluxe disc rewrites `UNIFORMS.DAT`,
  `STADIUMS.DAT`, `FIELDART.DAT`, `DB_TEAMS.DAT` and `TEMPLATE.DAT` and the
  game plays [S]. That disc's rebuilt containers even carry two defects the
  retail disc does not (§7), and it still ships. This raises the prior; it does
  not close the question.

**Codec 3.** Reported in NASCAR Thunder 2004 PS2 and implemented by nobody [S].
Absent from all seven discs here [M].

**`MMAP` pixels**, `SMF`/`DMF` geometry, `BNKl` banks and `SCHl` streams. All
first-level identification only; nothing below a magic is decoded here.

**`HSH1`.** One container per disc. Its ten `u32` values are one per member and
its width fields say 4 bytes, which reads like a name-hash lookup [A]; the hash
function is not identified.

---

## 7. The Deluxe disc: two defects a reader must survive [M]

Measured on `Madden NFL 09 Deluxe (USA).iso`, the community's rebuilt image.

**Six containers are recorded short in ISO9660.** Their directory record is 4
to 26,168 bytes shorter than their own `DATA` chunk declares — `UIS_PLYR.DAT`
by 4, `FIELDART.DAT` by 18, `TEMPLATE.DAT` by 60, `UIS_STAD.DAT` by 4,052,
`DB_TEAMS.DAT` by 26,168, and `MOVIEDAT.DAT` recorded as 200 bytes against 832.
The bytes are on the disc — ISO9660 extents are whole sectors — so a reader
that trusts the directory record silently loses every member past the cut.
`declared_length(head)` answers "how long does this container say it is" from a
few kilobytes, and `ea_terf_inspect.py` uses it to re-read the extent and says
so on stderr; all six then parse completely (`TEMPLATE.DAT`: 15 `TDB` + 3
empty; `UIS_PLYR.DAT`: 3,286 `MMAP`).

**Three of them under-count a trailing empty member.** `DB_TEAMS`, `MOVIEDAT`
and `UIS_STAD` declare a `DATA` chunk **exactly one 64-byte alignment unit**
shorter than their last member's aligned end — the signature of a rebuild tool
that does not give a trailing empty member its unit (§2.1 rule 3). No retail
container on any of the seven discs does this [M].

The game ships and plays this disc, so the engine evidently drives off the
directory rather than the `DATA` size. A tool must be tolerant of both:
`parse_terf(..., allow_size_mismatch=True)` accepts the mismatch and records
it, while still refusing any member that genuinely falls outside the bytes it
was handed.

**A writer takes the directory's view, and can.** Measured on all six: no
member with bytes ends past the record, only trailing empty members lie out
there, and the next file starts in the very next sector [M]. So
`rewrite_member(..., allow_short_tail=True)` and its `plan_member_rewrite`
twin work inside the bytes the record allocates: the `DATA` chunk's declared
size is written back exactly as the disc had it, the result is the same length
as the input, no member may move, and an empty member's slot past the record is
left alone — which means the ISO9660 record never has to change and a
fixed-allocation image writer is untouched. `parsed.short_tail` says how many
bytes the chunk declares past the buffer's end and `short_tail_is_empty`
whether anything but an empty member lives there;
`layout_violations(allow_short_tail=True)` forgives the one departure above and
nothing else. A container with real bytes past the record is refused, with both
sizes in the sentence, because that is the case where a rewrite really would
have to grow the file.

---

## 8. Cross-title: one reader, seven discs [M]

Containers under 96 MB (each disc's handful of speech and music containers are
skipped), read-only:

| disc | containers | members | stored | `LZH1` | `RLE1` | unknown codec | refused |
|---|---:|---:|---:|---:|---:|---:|---:|
| Madden NFL 09 | 101 | 36,195 | 31,926 | 4,269 | 0 | 0 | 0 |
| Madden NFL 09 Deluxe | 94 | 29,812 | 27,379 | 2,433 | 0 | 0 | 6 (§7) |
| Madden NFL 08 | 99 | 35,478 | 31,193 | 4,285 | 0 | 0 | 0 |
| Madden NFL 12 | 74 | 33,125 | 29,257 | 3,868 | 0 | 0 | 0 |
| Madden NFL 06 | 92 | 33,739 | 30,014 | 3,725 | 0 | 0 | 0 |
| Madden NFL 2004 | 51 | 14,981 | 11,700 | 3,281 | 0 | 0 | 0 |
| NCAA Football 09 | 80 | 17,485 | 12,975 | 4,077 | 433 | 0 | 0 |

Same three chunk chains, same four alignments, no codec outside 0/1/5 anywhere.
The package is therefore genuinely shared: a Madden 08, Madden 12 or NCAA
Football 09 module gets its container reader for free.

---

## 9. What RC87's lanes can build on

Against `GAME_STUDIO_SHELL_PLAN.md` §5:

1. **Inventory** (`ReadOnlyLane`, `read-only-mapped`) — **unblocked now.**
   Container walked, members enumerated with offset, size, codec, decompressed
   size and post-decompression format; digests are a `hashlib` call away. This
   is exactly what `ea_terf_inspect.py` prints.
2. **Uniform art** (`ArtLane`, `extract-only`) — **the container half is
   unblocked**, and the plan's format is corrected: 455 `MMAP` members in
   `UNIFORMS.DAT`, reachable and decompressed. What remains is the `MMAP` pixel
   payload (§4.2), which is that lane's own work; `parse_mmap_header` gives it
   dimensions and hands it the undecoded descriptor bytes.
3. **Text and team data** (writers) — **unblocked for the container**, which
   the plan gated on "TERF per-member compression and the container checksum"
   being settled. Compression is settled (§3). The checksum question is
   answered only as far as §6 allows, which is *not* far enough to promote a
   writer to `offline-writer-proved` — that needs the disc rebuilt and booted.
   The payloads are `TDB`, which this ecosystem already reads and writes
   byte-exactly: `DB_TEAMS.DAT` 235 databases, `TEMPLATE.DAT` 15, `GAMEDATA.DAT`
   104.
4. **Audio** (`extract-only`) — the container gives `SCHl` and `BNKl` members;
   decoding them is unchanged and still has no public writer.
5. **Stadiums, playbooks, gameplay** — inventory first, and inventory works.

### Still blocked, and by what

| blocked | by |
|---|---|
| ~~shrinking a member back down after an edit~~ | **unblocked**: `lzh1_compress` (§5.3) re-encodes at about EA's own size, 1,836 of 1,836 members proved |
| promoting any on-disc writer above `offline-writer-proved` | the boot test in §6 has not been run; it needs the rig |
| ~~an edit to a container named in `GAME.QKL` / `FE.QKL`~~ | **unblocked**: `containers.preload_copies(image)` reads the two `QL01` caches and returns, per container, every header copy and every member copy with its offset. Measured on the retail disc: **6,270 copies across 39 containers**, every one byte-identical to what it copies, and every one resolved — a row naming a member past the end of the container it names is attributed to whatever its bytes actually equal, which for the two such rows on this disc is the next file's container header. `UNIFORMS.DAT`'s directory is copied **three times** and none of its members at all, so a member rewrite is free only while the container's first `data_offset` bytes stay put — and they move the moment a member changes stored size or codec. The uniform-art writer rewrites every stale copy and refuses a carried member whose stored size changed, because a cached copy is a fixed slot |
| `MMAP` pixels, `SMF`/`DMF` geometry | not decoded anywhere here (§6) |

---

## 10. Sources

- **The owner's `nfl-online-revival`** (read-only reference on this box; no
  licence file, so nothing was copied — see the module docstring):
  `tools/lzh1.py` (the `LZH1` and `RLE1` decoders and the codec-id table,
  reversed from Madden NFL 2004 `SLUS_207.52` and NCAA Football 2004
  `SLUS_207.19`), `tools/madden_tdb.py` and `tools/container_census.py` (the
  container walk and the first-level format classifier),
  `docs/madden09-container-census.md` (the 47,769-member census, the `QL01`
  preload-copy finding, the `HSH1` and `BIGF` layouts),
  `docs/lzh1-encoder-design.md` ("No encoder was written"),
  `docs/cross-title-portability.md` (the codec id → name mapping).
- **aluigi's `madden_terf.bms`** — QuickBMS script; the per-member codec
  dispatch (`0` stored, `1` `TDCB_silence`, `5` `ea_madden`) and the confirmation
  that compression is per member. `https://aluigi.altervista.org/bms/madden_terf.bms`
- **QuickBMS 0.12.0 source**, `src/included/ea_madden.c` — the `ea_madden`
  implementation is a lifted x86 blob, but its static deflate ladders are
  readable and were matched against RFC 1951.
  `https://aluigi.altervista.org/papers/quickbms-src-0.12.0.zip`
- **Game Extractor**, `Plugin_DAT_TERF.java` (GPL, Java) — an independent
  reader *and writer* covering all header-size variants.
  `https://github.com/wattostudios/GameExtractor/blob/master/src/org/watto/ge/plugin/archive/Plugin_DAT_TERF.java`
- **WATTO's 2005 Xentax post** — the original byte-level write-up of the three
  `TERF` variants. `https://web.archive.org/web/2020id_/http://forum.xentax.com/viewtopic.php?t=1168`
- **StingRay68 on FootballIdiot** — the 16-byte `TERF` header field by field.
  `https://web.archive.org/web/20250118161627/http://footballidiot.com/forum/viewtopic.php?f=13&t=2897`
- **antdroid, "NCAA PS2: how to construct in-game…"** — EA's own name for the
  format: "DAT files are also known as TERF files."
  `https://www.antdroid.dev/2022/11/ncaa-ps2-how-to-construct-in-game.html`
- **DAT File Replacer (DFR)** by JDHalfrack — the closed-source tool the NCAA
  NEXT and Madden Deluxe teams use to rebuild these containers. No source has
  ever been released; §7's two defects are most likely its signature.

There is **no published specification** for `TERF` on any file-format wiki; the
sources above are the whole public record, and the byte-level detail in §2 is
this project's own measurement.

---

## 11. Verifying this

```
python tools/ea_terf_inspect.py --selftest
python -m unittest tests.mod_editor.test_ea_terf
python tools/ea_terf_inspect.py --iso "Madden NFL 09 (USA).iso" \
                                --path /DATA/UNIFORMS.DAT
```

The self-test and the 56 unit tests build every container they read, so both
run on a machine that owns none of these games. Only the third command needs a
disc, and it never writes to one.
