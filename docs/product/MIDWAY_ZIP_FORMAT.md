# Midway's stored ZIP and its `.ZIH` index — NFL Blitz 2002 and 2003 (PS2)

Both discs keep the **whole game** in one ZIP whose every member is stored, with
a pre-built index beside it: `/DATA/BASSETS.ZIP` + `/DATA/BASSETS.ZIH` on NFL
Blitz 2002 (`SLUS-20051`) and `/DATA/BERTHA.ZIP` + `/DATA/BERTHA.ZIH` on NFL
Blitz 2003 (`SLUS-20474`). 2,426 members and 2,695 members; the ZIP is 361 MB
and 439 MB and the index is 119,899 and 68,452 bytes [M]. Everything a modder
could want — rosters, crowd tables, trivia, playbook text, every RenderWare
texture dictionary, the sound bank — is a member of it.

The index is the ZIP's central directory **rewritten for fast seeking**: its
offset column points straight at each member's *data*, one local file header
past the signature, so the game never parses a ZIP structure at run time.

The implementation is `mod_editor/games/_formats/blitz_zip.py` (pure Python,
Qt-free, standard library only), with `tests/mod_editor/test_formats_blitz_zip.py`
covering it on **synthetic archives only** — 17 tests, every byte built by
`build_synthetic_zip` / `build_synthetic_index`, in both index shapes.

**Evidence tags.** **[M]** measured by running this module against a disc this
project can reach. **[S]** sourced. **[A]** assumed — a question, not a fact.

**Retail-free.** Constants, offsets, counts, digests and refusal sentences. No
member's bytes and no member name from either disc is reproduced here.

---

## 1. The verdict, in six sentences

1. **The pair is measured exhaustively, not sampled** [M]: all 2,426 and all
   2,695 index entries match the archive on names, sizes and data offsets; every
   member is *stored*; every local header's extra field is empty; the index walk
   consumes its file to the last byte on both discs.
2. **There are two `.ZIH` shapes and the disc does not decide which** (§4). NFL
   Blitz 2002 writes **inline** records — nine `u32` then a NUL-terminated name,
   **with a CRC-32 column**. NFL Blitz 2003 writes a **table** — three `u32` per
   record and one string pool at the end, **with no CRC column at all**. The
   reader tells them apart from the bytes: in the table shape the first record's
   first word is the directory's own length, `entries * 12` [M].
3. **A member is located by arithmetic and then verified against the archive**
   (§5): `offset - 30 - len(name)` lands on a `PK\x03\x04` local file header
   whose stored name equals the index's, on 2,426 of 2,426 and 2,695 of 2,695
   [M].
4. **Because every member is stored, a same-length replacement can be written
   where it lies** — and its CRC-32 then lives in **three** places on the 2002
   disc and **two** on the 2003 one (§6). `plan_member_replacement` returns every
   range or refuses; there is no path through this module that writes one
   without the others.
5. **The writer's declared-range count differs by disc — 4 on 2002, 2 on 2003 —
   and that is not a bug, an approximation, or a property of the edit** (§7). It
   is the CRC column's absence propagating all the way out to the ISO writer,
   and §7 is the paragraph a future writer must read before assuming either
   number.
6. **Both are proved on the retail discs, offline** (§8): four chained builds
   per disc, each verified by a verifier that imports none of the patcher, every
   member byte-identical but the one the receipt names. **Nothing has been
   booted.**

---

## 2. The pair, and the order it is read in [M]

```
/DATA/<NAME>.ZIP     a ZIP, every member stored (method 0), read through its
                     end-of-central-directory record and central directory
/DATA/<NAME>.ZIH     u32 entries, u32 body bytes, then the records
                     body bytes + 8 == the file, on both discs
```

`read_zip(read, size)` takes a **`read(offset, length) -> bytes` callable**, not
a path, so a caller holding the archive inside a 1.4 GB disc image hands it a
window and nothing is copied. Only the central directory and one 30-byte local
header per member are read, so opening a 361 MB archive costs about the size of
its directory.

The two files are joined **by name and never by ordinal**: the index's records
are sorted by name and the ZIP's by data offset, and the two orders differ on
both discs [M]. `cross_check` reports both orderings as booleans so a caller can
see that for itself.

---

## 3. The ZIP half [S: PKWARE APPNOTE 4.3; M: the two discs]

Nothing exotic: a standard ZIP written by a tool that never compresses.

| structure | what this module reads |
|---|---|
| end-of-central-directory (`PK\x05\x06`) | entry count, central directory offset and byte count, found by `rfind` in the last 66,000 bytes |
| central file header (`PK\x01\x02`) | compression method, CRC-32, packed and plain size, name, and the local header offset at +42 |
| local file header (`PK\x03\x04`) | the 30-byte fixed part only, for its name length and extra length, which give the data offset |

Every member's identities, exhaustively [M]:

| identity | 2002 | 2003 |
|---|---:|---:|
| compression method is *stored* (0) | 2,426 | 2,695 |
| packed size equals plain size | 2,426 | 2,695 |
| the local-header offset lands on `PK\x03\x04` | 2,426 | 2,695 |
| the local header's **extra field is empty** | 2,426 | 2,695 |
| `data_offset + size` is inside the archive | 2,426 | 2,695 |

**The empty extra field is load-bearing**, which is why the synthetic builder
writes the archive by hand instead of using `zipfile`: it is what makes
`offset - 30 - len(name)` the local header's address (§5), and `zipfile` would
add an extension field and quietly break that arithmetic.

`ZipMember` carries every offset a writer needs and computes none of them
twice: `data_offset`, `local_header_offset`, `local_crc_offset`
(`local_header_offset + 14`), `central_record_offset` and `central_crc_offset`
(`central_record_offset + 16`).

---

## 4. The `.ZIH` half — two shapes, told apart by the bytes [M]

```
+0x00  u32  entries          1 .. 1,000,000 or the file is refused
+0x04  u32  body bytes       body + 8 == the file, on both discs
+0x08  the records
```

### 4.1 Inline — NFL Blitz 2002

One record per member, variable length: **nine little-endian `u32`** then a
**NUL-terminated name**, the next record beginning at the byte after the NUL.

| word | what it is |
|---:|---|
| 0, 1, 2 | not interpreted [A] |
| 3, 4 | an MS-DOS time and date [A] — the same pair the ZIP's own headers carry |
| **5** | **CRC-32 of the member's stored bytes** |
| 6 | compressed size |
| **7** | **uncompressed size** — the size column this module uses |
| **8** | **data offset** — the member's payload, not its local header |

The walk is sequential and there is nothing to seek by, so `read_index` stops
when it has read the declared number of records and reports
`consumed_whole_file`, which is **true** on the retail disc [M].
`IndexEntry.crc_offset` is `record_offset + 20`, and it is the only reason a
writer ever touches this file.

### 4.2 Table — NFL Blitz 2003

A fixed 12-byte directory of `entries` records followed by **one string table**:

| word | what it is |
|---:|---|
| 0 | **name offset**, measured from +8 — i.e. from the end of the header |
| 1 | **size** |
| 2 | **data offset** |

**There is no CRC column.** Not a zero column, not an unused one: the record is
twelve bytes and all three are accounted for. A writer must not invent one.

### 4.3 How the shape is decided

Not by the disc's name, not by a flag, and not by the file's length:

```python
if 8 + entries * 12 <= len(data):
    first = u32 at +8
    if first == entries * 12:
        shape = "table"
```

In the table shape the first record's name offset **is** the directory's own
length, because the string table begins immediately after the directory — so
the first name sits at exactly `entries * 12`. In the inline shape word 0 of the
first record is something else entirely and the test fails. That is the whole
discriminator [M], and it is the reason the same code opens both discs and the
reason §7's range count is decided by the file rather than by the module.

`ZihIndex.has_crc_column` is `shape == SHAPE_INLINE`, and every CRC-carrying
path in this module is gated on it.

---

## 5. Locating a member, and checking that you did [M]

The index's offset column points at the member's **data**. To get from there to
the ZIP structure:

```
local header address = data_offset - 30 - len(name)          [M, both discs]
```

30 is the fixed part of a local file header [S: APPNOTE 4.3.7] and the name
follows it; the extra field is empty (§3), so there is nothing else in between.
`cross_check` measures this the other way round — it derives every member's data
offset from the archive's own local headers and compares — and reports:

| identity | 2002 | 2003 |
|---|---:|---|
| `offset - 30 - len(name)` is a `PK\x03\x04` header | 2,426 | 2,695 |
| … whose stored name equals the index's name | 2,426 | 2,695 |
| index names equal the archive's, as sets | 2,426 | 2,695 |
| index sizes equal the central directory's | 2,426 | 2,695 |
| index offsets equal the archive's own local-data offsets | 2,426 | 2,695 |
| index CRC column equals the central directory's | **2,426** | **no column** |
| recomputed CRC-32 over the stored bytes agrees | **600 of 600** | no column |
| index order is by name | true | true |
| archive order is by data offset | true | true |

The first two rows are the arithmetic above, measured on each disc and recorded
in the reader's own identity table; the rest are what `cross_check` returns on
each disc today [M].

**The CRC recomputation is bounded on purpose.** `cross_check(..., crc_sample=n)`
recomputes the CRC-32 of the `n` **smallest** members under `CRC_CHECK_LIMIT`
(4 MB) and reports how many agreed; `crc_sample=0` skips it. The bound exists
because one member is a 137,538,180-byte Midway sound bank and a census that
read it would spend all its time there [M]. A caller that wants that member's
bytes asks for them explicitly through `StoredZip.member_bytes`.

---

## 6. The writer: one member, the same length, every CRC site [M]

`plan_member_replacement(archive, index, name, payload)` returns a
`Replacement` — **nothing is written until `apply_member_replacement` is
called** — carrying two lists of `(offset, bytes)` pairs, each **relative to its
own file** so a caller holding both inside a disc image adds its own bases.

A payload of any length but the member's is refused:

> `<name>` occupies *n* bytes on the disc and the replacement is *m*; a stored
> ZIP member is rewritten where it lies, so give it exactly *n* bytes.

That refusal is the whole reason this format is safe to write at all. Growing a
member would move every later member's data, every later local header, the
central directory, the EOCD offsets, and every offset column in the index —
which is a rebuild, not an edit.

What a plan changes, and where:

| file | range | on 2002 | on 2003 |
|---|---|---:|---:|
| ZIP | the member's payload, at `data_offset` | ✓ | ✓ |
| ZIP | the local file header's CRC-32, at `local_header_offset + 14` | ✓ | ✓ |
| ZIP | the central directory's CRC-32, at `central_record_offset + 16` | ✓ | ✓ |
| `.ZIH` | the index record's CRC-32, at `record_offset + 20` | ✓ | **absent** |
| | **`zip_ranges` / `index_ranges`** | **3 / 1** | **3 / 0** |

Before it plans anything, it re-checks the pair against itself for **this**
member — the index's size and data offset must equal the archive's, or it
refuses with "the pair disagrees and no edit is safe until it does not". A pair
that has already been edited by something else is not a base to edit from.

`apply_member_replacement(zip_blob, index_blob, plan)` writes the plan into two
mutable buffers, bounds-checked against each buffer's length, and **refuses if
the plan carries index ranges and no index buffer was given** — which is the
mechanical statement of "you do not get to write two of the three".

---

## 7. What the writer declares — and why it is 4 ranges on one disc and 2 on the other

**This is the detail a future writer must not get wrong**, because both numbers
are correct and neither is a property of the edit.

There are **two** different range counts in play and they are one layer apart:

| layer | what a "range" is | 2002 | 2003 |
|---|---|---:|---:|
| **member** (`Replacement`) | a byte run inside the ZIP or the `.ZIH` | 3 in the ZIP + 1 in the index | 3 in the ZIP + 0 |
| **image** (`DeclaredRange`) | what the ISO9660 writer admits to having written | **4** | **2** |

The image layer is the one a receipt prints and a verifier enforces, and it does
not count member edits at all. Both files are whole ISO9660 files, so a build
hands the *whole rewritten file* to `tools/ps2_iso9660_writer.py`, which declares
**two ranges per file it replaces** [S: the writer's own contract]:

* `extent:<path>` — the file's allocated extent, the new content plus its
  zero-filled tail;
* `dirrec_length:<path>` — the 8 both-endian bytes of that file's declared
  length in its ISO9660 directory record.

So the arithmetic is **two ranges per rewritten file, and the number of
rewritten files is the number of files that carry a CRC-32**:

| disc | files rewritten | declared ranges | declared bytes |
|---|---|---:|---:|
| NFL Blitz 2002 | `BASSETS.ZIP` **and** `BASSETS.ZIH` | **4** | 361,524,828 |
| NFL Blitz 2003 | `BERTHA.ZIP` only | **2** | 439,045,798 |

and the declared bytes are the two files' own lengths plus 8 bytes of directory
record each: `361,404,913 + 119,899 + 16` and `439,045,790 + 8` [M].

**Which one applies is decided by the index's own record shape and never by the
disc's name.** `plan_ranges` and `build_replacements` put the index into the
replacement map only `if any(row["index_ranges"] for row in rows)` — that is,
only if `plan_member_replacement` found a CRC column to rewrite. Three ways to
get this wrong, all of which the code avoids by construction:

1. **Rewriting the `.ZIH` on the 2003 disc anyway.** It would be a byte-identical
   file, but the receipt would declare 4 ranges where 2 were needed, and a
   declared range that was not necessary is a range a reviewer cannot
   distinguish from an undeclared change somewhere else.
2. **Assuming 4 and hard-coding it.** A verifier that required four ranges
   would fail every honest 2003 build.
3. **Assuming 2 and skipping the index.** On the 2002 disc that leaves an index
   whose CRC-32 column disagrees with the archive it describes — the quiet
   failure this whole document exists to prevent. The independent verifier
   catches it: it re-derives the index from the destination's bytes and requires
   `crc_column_agrees == len(members)` **whenever the destination's index has a
   column**.

The declared bytes are also a **superset** of what actually changed: a 25-byte
crowd-table line edit declares 361,524,828 bytes on the 2002 disc, because the
writer's unit is the extent and not the edit. The receipt names the member, its
offset, its length, its old CRC-32 and its new one, which is where the real
edit is stated.

---

## 8. What is proved [M]

**In CI, on a synthetic disc**, in both index shapes: 17 format tests, plus each
module's own lane tests, plus 296 of 296 conformance checks per game. The 2003
module builds its synthetic source with the **table** shape on purpose, so the
shape difference is exercised rather than asserted.

**On the retail discs**, four chained builds per disc — read-only source,
scratch destinations, each image carrying every edit before it, each verified
against its own source, every image deleted afterwards:

| step | lane | 2002: ranges / bytes | 2003: ranges / bytes |
|---|---|---:|---:|
| 1 | `identity.crowd_tables` | 4 / 361,524,828 | 2 / 439,045,798 |
| 2 | `gameplay.field_table` | 4 / 361,524,828 | 2 / 439,045,798 |
| 3 | `playbooks.trivia_banks` | 4 / 361,524,828 | 2 / 439,045,798 |
| 4 | `rosters.player_names` | 4 / 361,524,828 | 2 / 439,045,798 |

Every destination is exactly the source's length. The verifier imports none of
the patcher: it re-derives the archive and the index from the destination's own
bytes and requires all 2,426 / 2,695 members present at their original offsets
and lengths, every member the receipt did not name **byte-identical by streaming
digest** — including the 137 MB sound bank, which is exactly where an undeclared
change would hide — the replaced member's bytes to recompute to the CRC-32 that
every site now carries, and the image-level claim to hold under
`tools/ps2_iso9660_verify.py`'s own ISO9660 decoder.
`docs/product/measured/nflblitz200{2,3}_ps2/writer-trial.json` carries both runs.

**Nothing has been booted.** No image rebuilt by either module has been run in
an emulator or on hardware, and no receipt claims otherwise.

---

## 9. What is not read

* **Any member's contents.** This is a container reader. What is inside a member
  is another package's business — `rw_txd` for the texture dictionaries
  (`docs/product/RENDERWARE_TXD_FORMAT.md`), the games' own `containers` for the
  text, roster and camera members.
* **`WIFF` interiors.** A big-endian RIFF; the `u32` after the tag plus 8 is the
  member on 190 of 190 and 209 of 209 [M] and the form type is `WIPS`, `WOMS` or
  `WOM `. **No chunk inside one is read.**
* **`CPTH` camera-record field meanings.** `16 + records * 32 == the member` on
  85 of 85 and 88 of 88 [M]; header word 1 takes four values (7, 1, 5, 3) and is
  reported unnamed; a record's 32 bytes read as IEEE floats and **which is a
  position and which a time is not measured**.
* **`.dff` geometry.** The top-level clump walk is in
  `RENDERWARE_TXD_FORMAT.md` §2.1; meshes, materials and frames are not read.
* **4-bit rasters**, `RENDERWARE_TXD_FORMAT.md` §5 — 6,231 and 5,436 of them.
* **`RYWM` (36 / 37 `.rsc` members)** and **`EKAB` (4 / 5 `.ban` members)**.
  `EKAB`'s `word1 + 8 == the member` holds on 4 of 4 and 5 of 5 [M]; that is the
  only thing read of either.
* **`mslasset.ms2`**, the 137,538,180-byte Midway sound bank. Named, never
  opened.
* **`.ZIH` inline words 0, 1 and 2**, and the MS-DOS timestamp pair at 3 and 4
  [A]. Carried, never interpreted, never rewritten.
* **Whether the game validates any of these CRC-32s at load time.** Nothing here
  has booted an image, so "the index must agree with the archive" is an
  invariant of the *files*, argued from the fact that the disc keeps the value in
  three places, and not a measured statement about the game's loader [A].

---

## 10. What a writer would need

Everything a **same-length member replacement** needs is here and proved offline
(§6, §8). What a *larger* member would need, and why it is not offered:

* every later member's payload moves, so **every local file header offset in the
  central directory** changes;
* the **central directory's own offset** and the EOCD record that names it
  change;
* **every index record's data-offset column** past the edit changes — and on the
  2003 disc, every **name offset** too, because the string table moves with the
  directory if the record count changes;
* the ZIP grows, so the ISO9660 file grows, so the **extent moves or the image
  is rebuilt** — `ps2_iso9660_writer` is a fixed-allocation writer and refuses a
  file that no longer fits its extent;
* and none of it can be checked against a game that has never been booted.

A **new member** additionally needs whatever the game's own loader expects of
the index's uninterpreted words (§9), which is not known.

The honest boundary is therefore exactly where the module draws it: same length,
in place, every CRC site, one new image, declared to the byte.

---

## 11. Refusals

Every refusal is a `mod_editor.games.contract.Refusal` (subclass
`BlitzZipError`) carrying **one sentence naming the condition**, re-raised
verbatim and asserted by the tests: a `.ZIH` too short to hold a header and one
record; an entry count outside 1..1,000,000; a body word that plus 8 is not the
file; a record whose name is not NUL-terminated inside the file; a declared
count the walk could not reach; no end-of-central-directory record in the last
66,000 bytes; a central directory that runs past the file; a central record
without its signature; a member whose compression method is not *stored*; a
member whose two sizes differ; a local-header offset that is not a local file
header; a member whose data runs past the file; a name that is not in the
archive (or not in the index); a replacement payload of the wrong length; a pair
whose index and archive disagree on a member's size or offset; a plan applied to
a buffer it was not made against; and a plan with index ranges applied without an
index buffer.

---

## 12. Verifying this

```bash
PYTHONPATH=. python tests/mod_editor/test_formats_blitz_zip.py   # 17 tests, synthetic only
```

The disc numbers are reproduced by opening each image's pair with
`blitz_zip.read_zip` and `blitz_zip.read_index` and calling `cross_check`; they
are recorded in `docs/product/measured/nflblitz2002_ps2/zip-index.json` and its
2003 twin, and the builds in the `writer-trial.json` beside them. **No member
from either disc is committed, and the tests do not need one.**
