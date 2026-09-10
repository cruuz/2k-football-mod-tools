# APF 2K8 MASTER PLAY: native encoding and bounded authoring

2026-09-09. **PROVED offline; every new design is UNWITNESSED in-game.**
This research targets the USA Xbox 360 disc and BASE executable. No executable,
title update, emulator, user save, or retail pack was modified. The new panel and
build adapter require the protected-file integration described in `WIRING.md`.

## Reproduction and identity

Run from the repository root, substituting the user's read-only inputs:

```sh
python3 tools/apf_play_format_proof.py --index "$APF_RETAIL_INDEX" --pe "$APF_FLAT_PE" --output docs/research/apf_play_format_derived.json
python3 tests/mod_editor/test_apf_play_designer.py
```

The proof tool emits semantic fields, names, offsets, counts and hashes, never
retail byte arrays. Its JSON contains all **586 plays, 163 formations, 4,948
nodes by opcode/count, all 38 conversion failures, and all 29 callback entries**.
The complete 182,096-byte body is rebuilt from parsed records, strings and
explicitly opaque fields, and must match the input byte for byte. This proves
lossless storage, not complete gameplay semantics for every field.

| Input | Identity |
| --- | --- |
| MASTER | Outer 180, outer ID 487346054, inner `mpb` / `PLAY`, file ID `0x33CDF8E3`, type hash `0x681C330E` |
| Decoded body | 182,096 bytes (`0x2C750`), SHA-256 `2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891` |
| BASE flat executable | 54,001,664 bytes, SHA-256 `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf` |
| Executable addressing | `file_offset = VA - 0x82000000`; PE section raw offsets do not apply to this flat image |

`read_resource()` pins MASTER's identity and full decoded SHA, and all eleven
named CPU books' decoded SHAs and names. Generic codec/compiler functions accept
synthetic source hashes for testing; retail staging/build always passes through
the stricter resource reader.

## MASTER layout

Offsets below are relative to the decoded body. Integers are big endian except
the common resource header's little endian tokens. A signed relative pointer
stored at `field` resolves as **`field - 1 + stored`**. All pointers are recalculated
when their records or name targets move; changing only the endian is insufficient.

| Offset | Length / stride | Meaning |
| --- | --- | --- |
| `0x00` | `0x30` | Common header, preserved; `YALP` at `+0x0C`, LE tokens at `+0x10/+0x14`, UTF-16BE `mpb` at `+0x20` |
| `0x30` | 4 | Relative book-name pointer |
| `0x34`, `0x38`, `0x3C`, `0x40` | 4 each | Formation count 163, play count 586, category count 28, node count 4948 |
| `0x44` | `0x10` | Category records; name pointer, category byte at `+4`, eleven personnel role/depth codes at `+5..15` |
| `0x244` | `0xB8` | Formation records; physical capacity 176 |
| `0x80C4` | `0x64` | Play records; physical capacity 640, current authoring limit 592 |
| `0x17AC4` | 8 | Assignment nodes; capacity 5400 |
| `0x22384` | variable | Sequential NUL-terminated UTF-16BE names; stock end `0x27840` |
| `0x28D84` | 84 | Unidentified relation, 176 rows: historical inspector interpretation reads 74 mask bytes and 10 opaque bytes |

There are 13 spare formations (2,392 record bytes), 54 physical play records
(5,400 bytes), 452 nodes (3,616 bytes), and 5,444 name-pool bytes. The existing
inspector bounds its 74-byte mask interpretation to 592 plays. The writer keeps
that bound, allowing **six appended plays**, rather than assuming all 640 are
safe. All newly occupied record/node space must be zero in the baseline.

A play contains a relative name pointer at `+0`, flags/type word at `+4`, a
feature word at `+8`, and eleven eight-byte assignments at `+0x0C`. Each assignment
has a BE descriptor followed by a relative node pointer. **Descriptor bits
31..28 give the chain length.** There are 6,446 assignments, 1,737 distinct starts;
lengths 2/3/4/5/6/7 occur 4,487/1,306/538/54/59/2 times. All 6,446 terminal nodes
carry flag `0x20`. Native node flags include alternate `0x80`, action `0x40`, and
terminal `0x20`; the NFL codec's low-bit flag interpretation must not be copied.
Other descriptor and flag bits are preserved, not manufactured.

The play type is `word(+4) >> 28`: stock offense 0 and defense 1. The live CPU
fetch path at `0x84869A74..80` loads and shifts that word. Earlier in the same
path (`0x84869A3C..68`), the `+8` feature word is tested at LSB-numbered bits 19,
10 and 15. Their complete meaning is not required by this writer: donor type,
features and descriptors are retained, and replacement must keep the old side.
There is no independently proved category field in a play. Formation and
personnel selection come from the containing CPU SPLB record.

A formation has name pointer `+0`, flags at `+4`, preserved word at `+8`, five
eligible slot indices at `+0x0C`, eleven slot-order indices at `+0x11`, two
reserved bytes at `+0x1C`, and eleven 14-byte alignment records at `+0x1E`.
Each alignment is `BE u16 tag, 3 * BE i16 x, 3 * BE i16 y`, in centimetres.
The default category is `(flags >> 18) & 63` (equivalently `byte(+5) >> 2`).
The reader at `0x84A9B914..38` consumes the primary coordinates. Commit
`24274c91` supplies the alignment codec/writer and distinguishes these slot
indices from personnel role codes. The new formation clones its donor's category,
eligible order, slot order, tags and opaque fields; this implementation does not
allocate a new personnel category or reinterpret `+0x11` as role codes.

## Native opcode proof and the 38 conversion failures

The previously missing APF callback table is **`0x820FBFC8`, 29 rows of 16 bytes**:
decode, encode, draw, validate. The matching BE flag table is **`0x820FBE68`**.
Registration at `0x84A877C8`, getter `0x84A87958` (signed opcode range `<29`), and
dispatch at `0x84A94078/98/F0` establish table ownership. This differs from the
NFL callback stride of 20. Flags agree with NFL except opcode `1C`: APF `0x210A`,
NFL `0x080A`. The derived JSON lists every callback address and flag.

The old conversion swapped each node's operand word and round-tripped through
the NFL object. **4,910 nodes survived; 38 changed. Every failure is opcode 1C.**
No stock node uses a numeric opcode outside `00..1C`; `00`, `0F`, `19` have no
stock instances, so corpus evidence does not establish their full semantics.

Failure indices, with individual body offsets, loss masks and hashes in JSON:

```text
2967 2969 2971 2973 2975 2977 2979 3005 3007 3009 3011 3019 3021
3023 3027 3029 3031 3813 3815 3817 3819 3821 3823 3825 3827 3829
3831 3833 3835 3837 3841 3843 3845 3849 3851 3853 3855 3857
```

Native `1C` decode `0x84A90EC0`, encode `0x84A91030`:

| Operand | Packed bits (LSB numbering) |
| --- | --- |
| Mode | 30..31 |
| First flag / lane | 5 / 0..4 |
| Second flag / lane | 13 / 8..12 |
| Selector | 16..19 |
| Seventh expanded operand | Constant zero |

The represented mask is `0xC00F3F3F`. Mirroring swaps the flag/lane pairs and
maps lane `v` to `16-v`; sentinel 17 stays 17. The native codec preserves all
unrepresented bits and header padding, although **zero stock nodes have remaining
opaque operand bits after native 1C decoding**. All 38 now round-trip natively,
and all 4,948 nodes and the whole body are exact. The UI calls 1C “Dual lane
assignment (APF)”; that bit proof does not establish a “spy” or match-coverage role.

## QB depth, routes and defensive assignments

`06` is Pass / first read. Its decoder at `0x84A91420` extracts bits 4..7;
`0x84A87E30..54` asks for expanded operand 1 and returns it plus 5, selecting
eligible player slots 6..10. **This is not a three-step/five-step switch.** The
writer exposes it as `first_read`, restricted to 1..5.

Physical QB movement before `06` is encoded in preceding `04` nodes. Decoder
`0x84A91230..1308` uses X = high byte minus `0x80`, Y = next byte minus `0x40`,
then multiplies by constants `12` (`0x82004498`) and approximately `2.54`
(`0x820B7538`), converting feet to centimetres. Native lateral calculations
also truncate and mirror. The codec uses reversible numeric coordinates for
storage; it does not emulate all float rounding or animation timing.
Changing Y changes the encoded physical drop landmark. No step-count/animation
consumer has been proved, so “five-step drop” remains deferred.

Route `12` decode `0x84A92F90`, encode `0x84A930A0`: low nibble is segment type,
bit 4 is a flag, high byte minus `0x40` is distance in feet, bits 20..23 are a
preserved selector. The drawing switch `0x84A97058` has 15 entries (`0..14`);
type 15 is refused. Type 0 continues straight; 4/5 turn in/out using the side
helper `0x84A94230` (`0x84A9735C/73BC`); type 6 takes the opposing 45-degree
corner branch (`0x84A9741C..74`); type 8 calls the curl helper `0x84A99BB8`
from `0x84A975E0`. Types 7/11 use a fixed backward movement with lateral offset.
The NFL subtype name “chip” for 8 must not be advertised as APF semantics.

Defense uses the same storage and ownership rules. Relevant stock opcodes:

| Opcode | Count | Native decoder / encoder | Supported authoring |
| --- | ---: | --- | --- |
| `0B` rush lane | 179 | `84A91F48 / 84A91FE8` | Lane bits 27..31, values 0..17; native mirror/sentinel verified |
| `0C` second rush lane | 32 | `84A92048 / 84A920E8` | Same numeric lane field |
| `0D` zone | 368 | `84A92148 / 84A922B0` | X/Y landmark bytes use the same biased feet conversion as movement |
| `0E` man | 134 | `84A92410 / 84A92550` | Cushion bits 4..11 minus 64 feet; preserve receiver/mode fields |
| `10` rush direction | 48 | `84A928B8 / 84A929E0` | Decode/re-encode and copy existing chain only |
| `1B` defense start | 727 | `84A90C20 / 84A90D78` | Decode/re-encode and copy only |
| `1C` dual lane | 38 | `84A90EC0 / 84A91030` | Explicit numeric mode, flags, lanes, selector |

The complete game validator has not been ported. Authoring preserves stock
chain shapes, descriptors and flags, isolates shared ownership and limits
editable fields. No claim is made about animation validity, route collision,
man matching, QB tracking, legal alignments, or a dedicated spy behaviour.

## The membership contradiction and CPU callability

`ASTRA_CONTEXT.md` describes a formation-to-play membership writer. That module
does not exist in this checkout. More importantly,
`tools/playbook_inventory.py:248` explicitly retracts the table's old name.
The fresh derived audit compares **11 named CPU books, 171 populated records,
6,727 entries** with MSB bits in row `formation_index` at `0x28D84`. Only
**1,650 entries (24.53%)** are covered; **zero records** are fully covered.
That refutes the asserted direct membership reading. The older comment's 209
records includes additional non-named/user resources; this proof intentionally
restricts writes/audits to the eleven named CPU books.

Edits and play replacements preserve this entire relation. A newly appended
formation copies its donor's complete 84-byte opaque row; this is conservative
clone construction, **not proof that the new row means formation membership**.
No newly invented mask bits are written. Runtime acceptance of new formations
remains an explicit test requirement.

The proved callable path is SPLB: 176 records at `0x70`, stride 176. Each has
84 BE u16 entries and an eight-byte trailer at `+0xA8`. Entry bits 9..0 name
the MASTER play; existing audible/X/Y tags are preserved. The trailer's first
word names the formation in bits 31..24 and category in 23..17; second word is
the category mask. The book mask is at `0x7E04`. Existing writer
`apf2k8_splb_writer.py` now accepts an optional reparsed MASTER play count;
existing callers still default to 586.

New calls use matching populated records, or an explicitly chosen empty record
plus populated donor record. Empty-row creation preserves donor trailer unknown
fields, requires identical personnel category and slot ordering, ORs the proved
category masks, and adds only requested plays. Offense goes to named `O-` books,
defense to `X-` books. No save addressing or U.S.E.R writes exist in this feature.
The static live CPU chain and formation resolution are documented in the supplied
playbook memory: fetch `0x848699D8`, choose `0x84869B20`, resolve `0x8486BC08`.
This shows where calls are sourced, not an in-game witness of these new records.

## Writer, transport and growth contract

The logical JSON plan stores names, indices, donor choices and numeric edits.
Compilation always starts from the pinned baseline. `current` may be baseline
or the exact intended result; another current state is refused. Project staging
stores one canonical JSON payload and one undo transaction; re-staging is a no-op.

Same-slot stock assignment copies delegate to the existing route writer,
including its orphan-start/relay guard. Unique chains are edited in place;
shared chains receive a private copy in the verified node-pool tail. Unrelated
plays keep their assignments. Names are rebuilt in existing order with every
relative pointer updated; name and node capacities are checked before returning.
Verification reparses independently, reproduces the intended transform, checks
owned byte ranges, and checks requested names, coordinates and node fields.

MASTER is one file in one H7A block: 84-byte IFF header, 20-byte H7A wrapper,
90-byte name footer, fixed **57,344-byte** allocation at virtual/local 0A offset
19,273,728 (block 9411, 28 blocks). Compression compares token preservation and
the existing greedy/optimal encoder. Each candidate must decompress exactly;
every match must have `length <= distance`. Rebuilt IFF is reparsed, file ownership
must be unchanged, and the padded outer allocation must fit. MASTER and all CPU
entries are compiled in memory before the build adapter returns any replacement.

| MASTER case | H7A payload | Active bytes including header/wrapper/footer | Free allocation |
| --- | ---: | ---: | ---: |
| Stock on disc | 56,162 | 56,356 | 988 |
| Stock, reviewed optimal helper | 54,628 | 54,822 | **2,522** |
| Five concepts + defensive clone + formation | 55,096 | 55,290 | **2,054** |
| Same combined design, portable greedy fallback | 56,832 | 57,026 | **318** |

Combined output has 164 formations, 592 plays and 5,010 nodes. CPU outer 259
retains 396 bytes free (395 portable); outer 618 retains 1,018 (1,017 portable).
The full derived receipt is `apf_play_design_build_derived.json`. The optimal
helper is the repository's reviewed Linux binary, SHA-256
`9061866e31f1a2930eceaa4fb8652ef1b7aa9b04cbce0174cc0eae125f8e49ab`.
The portable test proves this design fits without it, not universal Windows fit.

The inspected `nfl2k5_formation_play_writer.py:1..32,552..615` actually creates
records inside fixed capacity and manages names/nodes there; it does not provide
a general APF resource-relocation implementation. APF's outer pack format can
represent relocation: `tools/apf_outer.py:184..211,243..290` reads a `0x18` header,
16-byte pack descriptors, and 12-byte `(name_id, offset_blocks, size_blocks)`
entries over concatenated packs. A future BUILT-copy writer can append aligned
space to the **last pack (1B)**, increase that descriptor's block count, and repoint
outer 180's virtual offset/size without moving other packs' virtual starts.
It must independently verify directory ownership, every old entry, new bounds,
all inner pointers, and runtime loader acceptance. Growing an earlier pack would
shift later virtual starts. Adding another H7A block alone would not increase the
PLAY tables' fixed capacities. **Relocation is a documented design, not a shipped
or runtime-proved writer.** It is unnecessary for the bounded appends delivered.

## Concept recipes that actually compile

`apf2k8_play_concepts.py` provides five authored recipes, not placeholders. They
clone I Pro play 10 (`50 TE/Z Curls`), keep its protection and read descriptors,
and use play 20's same-slot FB route skeleton to avoid a conditional six-node
FB assignment. Each changed receiving slot has Start + two Route Segment nodes.
QB movement Y is -21 feet; first read remains the donor's selector. Names and
complete authored numeric recipes are source code, with no embedded retail nodes.

Each cell gives **straight stem feet / turn type / turn distance feet**. Slots
6/7/8/9 in I Pro are TE, left WR, right WR, FB by the donor's personnel/geometry.

| Recipe | Slot 6 | Slot 7 | Slot 8 | Slot 9 |
| --- | --- | --- | --- | --- |
| Smash | 30 / corner 6 / 45 | 15 / curl 8 / 6 | 36 / in 4 / 45 | 3 / out 5 / 15 |
| Levels / Drive | 30 / in 4 / 60 | 9 / in 4 / 60 | 18 / in 4 / 60 | 9 / out 5 / 30 |
| Dagger | 18 / straight 0 / 60 | 45 / in 4 / 60 | 9 / in 4 / 60 | 3 / out 5 / 15 |
| Curl-Flat | 3 / out 5 / 18 | 36 / curl 8 / 6 | 36 / curl 8 / 6 | 3 / out 5 / 18 |
| Mesh | 12 / in 4 / 60 | 30 / corner 6 / 45 | 15 / in 4 / 60 | 3 / out 5 / 30 |

Smash therefore encodes a 10-yard corner stem and 5-yard hitch/curl stem, with a
backside combination. Dagger includes the TE vertical and opposite dig; Mesh
uses crossings at four and five yards. These are explicit diagram/landmark
choices, not a claim that spacing, timing or receiver behaviour is correct in
game. Five-step cadence, Dagger pre-snap shifts, Pirate, and a true spy are
deferred. Noah must witness each concept, both field sides, CPU call selection,
new formation alignment and BASE/TU 1.1 separately before any runtime promotion.
