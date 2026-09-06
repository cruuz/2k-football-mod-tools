# Midway `PAK ` — the resource pack of NFL Blitz Pro and Blitz: The League (PS2)

Both discs keep every game asset except audio, video and code in one file, `RESIMG1.DAT`
(417 MB on NFL Blitz Pro, 506 MB on Blitz: The League). The file is a read-only file-system
image: a list of object records, the objects themselves, and a directory at the very end that
locates each object by byte range. Inside each object is a second directory of members — the
`.dbd`/`.dbs` databases that hold rosters, teams and playbooks, the `SEC ` containers that hold
plays and scenes, and the RenderWare art.

The implementation is three standard-library packages under `mod_editor/games/_formats/`:

| package | reads | tests |
|---|---|---|
| `midway_pak.py` | the pack: header, metadata list, trailer directory, objects, members | `tests/mod_editor/test_formats_midway_pak.py` |
| `midway_db.py` | a `.dbs` schema and its `.dbd` data: tables, rows, bit-fields, string pools | `tests/mod_editor/test_formats_midway_db.py` |
| `midway_sec.py` | a `SEC ` section container | `tests/mod_editor/test_formats_midway_sec.py` |

**Evidence tags.** **[M]** measured by running these packages against the two discs. **[S]**
sourced. **[A]** assumed — a question, not a fact.

**Retail-free.** Offsets, counts, field names and widths, refusal sentences. No row, no name
from either disc is reproduced here; every test builds the bytes it reads with the packages'
own `build_*` helpers.

---

## 1. The verdict, in five sentences

1. **Every object is located** [M]: the last 2,048 bytes of the pack are a directory whose
   leaves carry `(offset, size)` for each object, and those ranges tile the body from the
   first sector after the metadata list to the directory itself — 14 objects on Blitz Pro,
   57 on The League, of which 2 are absent from the metadata list.
2. **Every member is located and checked** [M]: 5,605 and 7,409 members, each named by the
   2,048-byte record before its data, each record agreeing with the directory entry that
   points at it, each sector-aligned, ascending, and meeting the next record at its padded end.
3. **The databases are read to the byte** [M]: 48 of 49 `.dbd` files on Blitz Pro and 311 of 311
   on The League walk against their schema with a zero trailer, and every one of the 29,178 +
   28,639 string references lands on a string start in the pool its schema names. The one
   refusal is a data file whose own schema is not on the disc, and it is refused by sentence.
4. **The `SEC ` containers are read to the byte** [M]: 1,104 of 1,104 on The League, 56,971
   sections, every section table contiguous and ending at the file's declared total.
5. **No writer exists.** A same-length member could be replaced at its own byte range; a longer
   one moves every later offset in the object's directory, the object's leaf in the trailer,
   every later object, and header word 2 — §6 says exactly which.

---

## 2. The pack, byte by byte [M]

```
+0x000  " KAP"                'PAK ' written as a little-endian u32
+0x004  u32  512              constant on both discs; not explained
+0x008  u32  body bytes       == file bytes - 2048 (checked)
+0x00C  u32  node-table bytes the trailer directory's node table (checked)
+0x010  u32  name-table bytes the trailer directory's name table, padded to 4 (checked)
+0x014  u32  metadata offset  2048 on both discs
        zero to 0x800

+0x800  u32 0x11111111, u32 records, then records x 2,048-byte slots
        -- each slot is a byte copy of one object's header record (14 of 14, 55 of 55)

        objects, each sector-aligned, laid out in the lexicographic order of their
        hexadecimal names ("84d99f8.of" sorts after "724efde6.of")

last 2,048 bytes: the directory, 16-byte nodes (name offset, kind, offset, size-or-count);
        kind 1 is a directory of `count` child nodes at `offset`, kind 0 a file of `size`
        bytes at `offset`; name offsets point into a NUL-separated name table that follows
        the node table.  The root ("") holds a directory "objects" whose leaves are the
        object files, and a file "resmeta.lf" whose range is exactly the metadata list.
```

Header word 3 is the node table's length and word 4 the name table's; they were the "two
unexplained counts" of the first reading of these discs.

The mapper's page for each disc quotes the identities the reader checks: first object at the
first sector after the metadata, objects tile to the directory, node/name table lengths equal
the header words, the `resmeta.lf` leaf equals the metadata region, metadata slots are byte
copies of the object records, and each record's `objects\<hex>.of` path stem equals its hash.

## 3. An object and its members [M]

An object begins with a 2,048-byte record: `u32 0x22222233`, `u32 name hash`, `u32 2048`,
`u32 member count`, a timestamp, then a triple `(u32 category length, u32 path length, 0)`
followed by the two NUL-terminated strings — a category word and `objects\<hex>.of`. Then
comes the member directory, padded to a sector, then the members: each a 2,048-byte
`0x11111111` record followed by its bytes, padded to a sector. Member offsets are relative to
the object's start and name the data, one record past the record.

Two generations exist and are told apart by measurement, never by title:

| | 2003 layout (NFL Blitz Pro) | 2005 layout (Blitz: The League) |
|---|---|---|
| object record timestamp at +16 | seven words: year, month, day, hour, minute, second, ms | one u64 of .NET `DateTime.Ticks` |
| string-length triple | +60 | +40 |
| directory entry | 64 bytes: `hash, 0, offset, size, char path[48]` = `modules\<object hex>\<member hex>.mf` | 32 bytes: `hash, 0, offset, size, hash2, u64 ticks, 0` |
| member record | size +64, hash2 +72, type word +76, module-string length +80, file name +88 then the module string | size +44, hash2 +52, type word +56, file name +68 |
| record dates measured | 2003-09-13 to 2003-09-27 | 2005-06-28 to 2005-09-14 |

`hash2` is a second 32-bit value that is not the CRC-32 of the member's bytes [M]. The name
hash is a function of the name — the same category word hashes to the same value on both discs
— but it is none of CRC-32, FNV-1/1a, djb2, sdbm, one-at-a-time, ELF or SuperFastHash [M]; the
reader carries it and never recomputes it, so adding a member is the one edit this format
cannot make honestly today.

What the members are, by extension (top, both discs) [M]:

| Blitz Pro | The League |
|---|---|
| `.dff` 2,229 and `.rtd` 1,641 (RenderWare section ids 0x10 / 0x16 [S]), `.cap` 345 (`HTPC`), `.ini` 306, `.ppn` 286 (`Part`), `.tga` 238, `.amx` 55, `.dbd` 49, `.dbs` 16, `.ban` 14, `.wad` 13 | `.rtd` 4,442, `.sec` 1,104, `.dbd` 311, `.dbs` 294, `.gcp` 286, `.cap` 282, `.wad` 274, `.ppn` 93, `.wip` 86 (`WIFF`), `.rws` 82 (RenderWare stream), `.sss` / `.str` 40 each |

## 4. The database pair — `.dbs` schema and `.dbd` data [M]

The schema is a flat token stream: `D<database>\0`, then per table `T<name>\0` (rows) or
`t<name>\0` (a string pool), then fields `<type><name>\0 u16 param`, ended by a NUL. Field
widths were settled by the arithmetic of 2,021 + 164 tables, all of which divide evenly:

| type | bytes | param |
|---|---|---|
| `b` `B` | 1 | `bits | shift << 8` when bit-packed, else 0 |
| `w` `W` | 2 | same |
| `i` `I` | 4 | same |
| `f` | 4 | 0 |
| `s` `S` | *param* | the fixed width (`S` is always 50 on both discs) |
| `r` | 4 | index of the pool table the offset points into |
| `q` | 2 | same, 16-bit offset |

A bit-packed field whose shift is not zero shares the previous field's storage unit:
`(6,0) (6,6) (5,12) (7,17) (7,24)` is five `i` fields in one u32; `(7,0) (1,7)` is two `b`
fields in one byte. Upper-case types look like key columns [A]; they are read like the
lower-case ones.

The data file repeats `char[32] database, char[32] table, u32 bytes, <bytes>` per table, in
schema order (a file may stop before the schema's last table), and ends with a u32 trailer that
is 0 on every file measured. A string field is NUL-terminated inside its width — the bytes after
the NUL are the writer's stale buffer, not zeros. A pool is NUL-separated with the empty string
at offset 0, and every `r`/`q` value measured lands on a string start.

What the roster databases hold, as table row counts [M]:

* **Blitz Pro** `Databases/playerdb.dbd`: `version` 1, `players` 3,628, `teams` 61, `positions` 15,
  `attributes` 10, `depthchart` 60, `coaches` 122, `cheerleaders` 366, `cameramen` 9, censor and
  allow word lists, and two pools `firstname_strings` / `lastname_strings` the player rows
  reference. `formation.dbd` `plays` 303 rows of a sprite-resource hash and one packed word.
  `Playbooks/master_pbk.dbd`: `playbook` 33, `condition` 1,033; 32 per-team playbook `.dbd`
  files share `master_pbk`'s schema and are matched to it by the database name in their header.
* **The League** `databases/playerdb.dbd`: `version` 1, `teams` 29, `positions` 15, `depthchart` 33,
  `voices` 28, `player_list` 695 (first and last name inline, 32-byte strings), `campaign_0_attribs`,
  `campaign_1_attribs` and `versus_attribs` 695 each, `cap_player_list` 40, `cheer_list` 252,
  `coach_list` 196, `prop_list` 123, `injuries` 23, `skin_colors` 77.
  `playbooks/master_pbk.dbd`: `playbook` 18, `condition` 244; `master_plays.dbd`: `plays` 364 with a
  description pool; 17 per-team `.dbd` files on `master_pbk`'s schema.

`Database.row()` returns a row as a dict — bit-fields unpacked, strings trimmed at their NUL,
references resolved to the pooled string — and `check_references()` is the identity the mapper
quotes. Signedness of the integer types is not established [A]; values are read unsigned.

## 5. The `SEC ` container [M]

```
+0x00  " CES"          'SEC ' as a little-endian u32
+0x04  u32 4           version
+0x08  u32 0
+0x0C  u32 0xCDCDCDCD  an uninitialised-memory fill the writer never cleared
+0x10  u32 sections
+0x14  u32 name-table bytes
+0x18  u32 total bytes == the file
+0x1C  sections x (u32 kind, u32 offset, u32 size, u32 name offset)
       name table, padding to 128, then the sections: contiguous, 128-byte multiples
```

Kind 4 sections are named `*.rws` (RenderWare streams, 1,678 of them); kind 2 sections carry
bare names (55,293). An empty container is 128 bytes: the header with zero sections and a
`PAD128` fill. The League's playbooks object holds 289 of these with 49,161 sections between
them — the plays; each stadium object holds one, its scene. Blitz Pro has none.

## 6. What a writer would have to keep consistent [M]

* **A same-length member**: its bytes only. Nothing else references them; `hash2` is not a
  CRC of the data and is not recomputed by the reader.
* **A longer member**: every later member's offset in the object's directory; the object's
  `size` in its trailer leaf; every later object's leaf offset; header word 2 (body bytes);
  and, on The League, the loose `RESMETA.LF` if any object record changes (it is a byte copy
  of the pack's list).
* **A new member**: the name hash, which is not known.
* **A database row**: fixed width, in place; a string that does not fit its width is a refusal,
  not a truncation. The trailer stays 0.

## 7. Refusals

Every reader raises `mod_editor.games.contract.Refusal` with one sentence naming the condition:
a header whose body word does not add up, a directory leaf that runs into the trailer, an
object whose record magic is wrong, a member record that disagrees with its directory entry, a
directory whose entry layout does not match its record's layout, a database whose file names a
different database than its schema, a table not in the schema, a byte count that is not a
multiple of the row width, a pool without its NUL, a missing trailer, a section that does not
start where the previous one ended. The tests assert the sentences.
