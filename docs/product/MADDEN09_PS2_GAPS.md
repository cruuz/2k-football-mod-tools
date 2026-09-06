# Madden NFL 09 (PlayStation 2) — the gap register

Six lanes were built for this module in one day and each left a measured gap.
This document takes every one of them, states its root cause with a citation,
says what would close it and at what cost, records what this pass closed
offline and what it could not, and ends with the ordered witness plan for the
owner, who does the boots.

**Evidence tags.** **[M]** measured — a read-only command was run against a
disc or a dump this box holds and the number is quoted. **[S]** sourced — a
cited finding, mostly the owner's static research in `nfl-online-revival`.
**[A]** assumed — inference, treat as a question.

**Retail-free.** Names of files, tables, fields and tags; offsets, widths,
counts, digests and hashes of hashes. No game string, byte or pixel.

**Status words.** *closed* — the missing fact is now measured and the code or
document carries it; *narrowed* — the gap is smaller and its remaining
missing fact is named exactly; *open* — nothing measurable on this box moves
it, and the missing fact is named.

| # | gap | status after this pass |
|---|---|---|
| 1 | texture identities depend on dumps | **closed** for the TEX0 half and for every power-of-two texture; open only for run-time CLUTs, region draws and one 26-texture class |
| 2 | MicroTalk speech | **open** — needs the codec's fixed tables and an oracle |
| 3 | bank writer | **narrowed** — stereo layout corrected, loop tags measured; open on how the SPU is handed a loop |
| 4 | playbook capacity, second layer | **narrowed** — the offline-provable route is named; open on one boot |
| 5 | geometry | **narrowed** — every `SMF` member carries its own name; geometry still undecoded |
| 6 | preload-cache semantics | **narrowed** — witness designed around one texture drawn on every coin-toss screen |
| 7 | identity blast radius | **narrowed** — the third `TEAM` copy is not cache-carried and can be written |
| 8 | text-lane granularity | **narrowed** — the `KEY=value` grammar is measured |
| 9 | roster units | **closed** — inches and pounds-less-160, offered on the page |
| 10 | container checksum | **narrowed** — no header word of the 13 rewritten Deluxe containers tracks content |
| 11 | presentation | **narrowed** — the overlay textures are on disc and named |
| 12 | Deluxe | **narrowed** — the database writers now build and verify on it; open only on two art containers over the read limit, and on a boot |
| 13 | `MMAP` palette banks, LZH1 worst case, ISO free space | **narrowed** — measured and scoped |
| 14 | nothing booted | the witness plan, §14 |
| 15 | the uniform verifier refused a recipe naming several images of one member | **closed** — the exemption is now the set of named images |

---

## 1. Texture identities depended on dumps

**Root cause.** A PCSX2 replacement filename is
`<tex0 hash>-<clut hash>-<bits>.png`, XXH3-64 over the GS's own texture and
CLUT memory. The first edition reproduced the CLUT half (XXH3-64 over the
de-interleaved palette) and paired the TEX0 half **by pixels** with a dump,
because what the emulator hashes for the texture half was not known: 3,024
disc textures identified from 33 dumped frames, 6,195 dump files unmatched,
every undrawn texture `None` [M, `MADDEN09_PS2_MODULE.md` §6.5].

**What PCSX2 hashes** [S, the emulator's texture cache; re-expressed and then
proved against the dumps rather than trusted]. The TEX0 half is a single
XXH3-64 state fed with the texture's **GS block image**: the 256-byte blocks
a 16×16 (8-bit) or 32×16 (4-bit) tile occupies, walked in row-major block
order, each block in the GS's column layout. A level smaller than a block in
either dimension, and any region-clamped draw, takes a second path — the
rectangle unswizzled to one byte per texel. With mipmapping on, the levels the
draw's LOD range reaches are fed into the **same** state after the base, so a
texture has one name per `(base level, level count)` chain. The `bits` word
is `PSM | TW<<6 | TH<<10`, with TCC in bit 14 only under the classic
convention, and the TEXA bits are zero for an indexed texture.

**What was built.** `mod_editor/games/_formats/pcsx2_texture_name.py` (the GS
block layout as two closed-form texel-to-offset functions, the two hashing
paths, chain enumeration, the CLUT hash, the name grammar both ways) and
`_formats/xxhash3_64.py` (XXH3-64, the twin of `tools/xxh3.py`, pure Python
with the C extension as an optional accelerator). The art lane derives every
image's names at catalogue time; `replacement_identity` answers a
dump-confirmed name first and a derived one otherwise, `replacement_identities`
keeps the two apart under `derived:` keys, and `identity_note` says which.
`tools/madden09_ps2_texture_identities.py --derive-check` re-derives the
identity table and censuses the disc; the result is
`docs/product/measured/madden09_ps2/pcsx2-texture-identity-derivation.json`.

**Proof** [M, retail disc, 33 dumped frames]:

| | |
|---|---:|
| dump-identified textures whose TEX0 hash the derivation reproduces | **2,994 of 3,024** |
| — of the 30 others: a shared picture the pixel matcher put on the wrong member; the hash names the right one | 3 |
| — of the 30 others: a dump whose only name is another surface's, of the other index width | 1 |
| — of the 30 others: single-level 128×64 8-bit textures, CLUT reproduced, TEX0 not | 26 |
| dumped names newly placed by hash that pixels could not place | **726** |
| dump-identified images after both methods | 3,283 |
| images on the disc the rule names (45 containers) | **12,378** (162,459 names, one per mip chain and convention) |
| images refused: width or height not a power of two | 3,978 |
| images refused: palette-only entries, direct-colour images with no palette, `IPU1`-packed, unreadable | 461, 625, 1,188, 6 |
| dumped (plain) names whose CLUT is a palette of the same member | 2,106 |
| — another member's palette | 238 |
| — a CLUT in no file: built at run time (263 of them 4-bit uniform sheets) | 265 |
| region-clamped dumped names, offset in no file | 1,824 |

The block layout was written from the GS's column structure and confirmed by
the dumps; it was not copied from another project's tables, and a folklore
formula in circulation for the same layout does **not** reproduce it, which is
one reason the dumps and not a citation are the proof.

**What closes the rest, and at what cost.**

* *The 26-texture class* (single-level 128×64 8-bit, one image each, named
  after a team, one 256-entry and two 16-entry palettes): the CLUT reproduces
  and the TEX0 does not, under both paths, both block orders and both index
  widths [M]. Hypothesis [A]: the game builds mip levels for these at load and
  the draw's LOD range reaches them, so the hash covers bytes no file holds.
  A GS dump of a frame that draws one, replayed with the emulator's texture
  cache logging on, would settle it in an hour; nothing offline can.
* *Run-time CLUTs* (265 names): the game composes the 16-entry palette of a
  4-bit uniform sheet from team colours at run time. The TEX0 half is right;
  the CLUT half needs the composition rule, which is executable behaviour —
  either a trace, or a dump per team as today. Cost: one frame per team, and
  the identities tool already ingests them.
* *Region draws* (1,824 names): the rectangle offset comes from the `CLAMP`
  register at draw time. A GS dump carries it; the disc does not. Cost: a
  region-aware pass over the 33 existing GS dumps (they are on this box) —
  about a day — and it would also settle the class above.
* *The pack itself*: load a pack built from derived names in PCSX2 and see the
  replacement drawn. That is the boot in §14 and the only thing between this
  row and offering the pack step.

**Status: closed** for what the brief asked — the names are derived from the
disc without a dump, the derivation is proved on the dumps, and the
dump-derived table stays as the confirmed layer. Open on the four items above,
each with its missing fact named.

---

## 2. MicroTalk

**Root cause.** 33,751 of the disc's 34,046 streams — every line of speech and
commentary — declare EA codec 4 at 1.706 bits per sample [M,
`EA_SCHL_FORMAT.md` §4]. ffmpeg refuses the codec by name, so the audio lane
refused it rather than guess.

**Is a decoder implementable from documented knowledge?** The codec is EA's
MicroTalk (the community's "UTK"), and it has been reverse-engineered in
public: a reference decoder exists in the game-music extraction tooling and
in a stand-alone decoder written from EA's own executables [S; neither is on
this box and neither was consulted]. So the *grammar* is documented, and a
decoder could be re-expressed. What cannot be re-expressed is the codec's
**fixed tables** — the reflection-coefficient quantiser and the excitation
codebooks — which are numeric constants that no amount of measuring the
streams recovers. A decoder written without them is not a decoder.

**What oracle exists without ffmpeg?** Three, in ascending strength:

1. *Self-consistency* [offline]: the parser consumes exactly the `SCDl`
   block's bytes and produces exactly its declared sample count for every
   block of every stream (34,046 streams, 0 counter-examples is the bar the
   EA-XA reader already met); decoded energy follows the block structure.
   This proves the framing, not the arithmetic.
2. *A second decoder* [offline, the owner]: extract one stream (`--export`
   already writes the raw member) and decode it with the public tooling on a
   machine that has it; byte-compare. This is the ffmpeg role, filled.
3. *A human listening* [the owner]: the weakest, and the one that catches a
   right-framed wrong-arithmetic decoder in a second.

**Cost.** Two to three days with a reference in hand; not finishable without
one.

**Status: open.** Missing fact: the codec's fixed tables (or a reference
implementation to re-express them from) and an oracle stream decoded by it.

---

## 3. The bank writer

**Root cause.** 301 `BNKl` banks, 967 sounds, all PlayStation ADPCM; the
encoder round-trips bit-exactly; the row stayed extract-only because 134
sounds carry tags read as loop points whose meaning was not established, 459
declare no sample rate, and the SPU's handling of a loop was unmapped [M,
`MADDEN09_PS2_AUDIO.md` §5].

**What this pass measured** [M, all 967 sounds]:

| fact | result |
|---|---|
| tag `0x89` — read as a loop tag | on exactly the **183 stereo** sounds, on none of the 784 mono; equals `0x88 + length/2` on **183 of 183** |
| each stereo run ends in a flagged frame (before `0x89` and in the last frame) | **183 of 183** |
| planar decode gives higher left/right correlation than interleaved | **181 of 183** |
| `0x86` (loop start) on a 28-sample frame boundary | 134 of 134 |
| `0x86 <= 0x87 <= 0x85` (start, end, count) with end never equal to count | 134 of 134 |
| `0x8A` | 0 on every sound; role not established |
| tags the 459 rateless sounds carry | `0x0E` in six values (40..120), `0x06` in six (5..95) — candidates for a rate or a volume, unproved |

The first finding is a **defect corrected**: stereo bank sounds are planar,
and the reader had decoded them as alternating frames — each frame's
arithmetic right (proved against ffmpeg), the channel assignment wrong, so
every stereo bank export scrambled its channels 28 samples at a time. The
decoder now splits at `0x89`, refuses a tag off a frame boundary, and the
synthetic stereo bank CI builds carries the tag.

**What would make the row a writer.** A bounded same-length replacement on the
streams lane's own path: the WAV re-encoded to PS ADPCM at the sound's declared
rate (rated sounds only — 508), each run written into its own bytes and
zero-filled to its length, `0x86`/`0x87` kept as they are (the encoder emits
whole frames, so a frame-aligned loop start stays aligned), and the 17
bank-carrying cache copies in `GAME.QKL`/`FE.QKL` rewritten by the path the
streams lane already proves on a synthetic cache [M]. Cost: about a day, and
it lands on `offline-writer-proved`.

**Status: narrowed.** Missing fact for a *looped* sound: how the SPU is handed
the loop (a boot with a replaced looped sound). Missing fact for a *rateless*
sound: which tag the game reads as its rate (a boot with `0x0E` changed on one
sound, or a trace).

---

## 4. Playbook capacity, the second layer

**Root cause.** The editor caps are five `sltiu` immediates and are translated
(`MADDEN09_PS2_CODE_PATCHES.md`). Below them the library takes a table's live
capacity from the on-disc header (`0x0081A2A4..`) [M], the insert guard
(`0x0082A098`) refuses with status 19 when count reaches capacity [M],
`table_set_capacity` (`0x0082A6A0`) has no immediate to raise — five of its
six callers pass it the capacity they just read [M] — and the database-open
hook is located, not pinned [S]. All 1,944 tables of the 102 shipped
playbooks have `record_count == max_records` [S].

**Two routes.**

*Runtime code* — a cave on the open path that calls `table_set_capacity` with
a scaled value. Needs the unpinned hook site, new MIPS, and a boot to verify
any of it; nothing offline can prove a cave correct. Cost: days, then boots.

*A grown on-disc table* — write a database whose table header declares
`max_records > record_count` and carries the extra record slots. Every piece
exists and is proved offline: `ea_tdb.build_tdb` takes a `max_records` per
table and `recompute_crcs` writes the four checksums; `ea_terf.lzh1_compress`
re-packs the grown member at about EA's size [M]; `rewrite_member` and the
ISO writer's opt-in relocation handle a member that grows past its slot;
`containers.preload_copies` finds the cache copies to keep in step — and for
`GAMEDATA.DAT` the caches carry **no** playbook member at all, only members
103–112 and two directory copies in `FE.QKL` [M]. The loader reads the on-disc
header into the live capacity [M], so a grown header is what raises it. And a
header with slack is a shape the game already loads: `TEMPLATE.DAT` member 13,
the create-a-playbook template, ships every playbook table at `record_count 0`
with `max_records` 20/100 [S].

**Which is provable offline.** The grown table. Its verifier is the roster
writer's: values read back, four checksums, every differing byte inside a
declared span, cache copies equal to what they copy.

**What one boot has to show.** With the five-word editor patch active and a
grown book on the disc: open that book in create-a-playbook and add a
**twenty-first set**. The prediction is that the editor accepts it and the
library, now with slack, inserts the row instead of returning status 19; the
recorded outcome — the set appears, or the same message, or a different one —
is the finding. If the game refuses to *open* the grown book at all, the
finding is that something beyond the header (a CRC consumer on the open path,
§4 of the owner's playbook map) checks the shape, and the hook question is
back.

**Status: narrowed.** Not built this pass: the playbook lane is being
integrated on a parallel branch, and a table-growing writer belongs to it.
Missing fact: the one boot above.

---

## 5. Geometry

**Root cause.** `SMF` (651 in `STADIUMS.DAT`, 642 in `FIELDART.DAT`, 154 in
`STADATA.DAT`) and `DMF` members have no decoder and no public layout [M].

**What the bytes say** [M, all 1,447 `SMF` members]:

| field | evidence |
|---|---|
| `+0x00` `SMF\0` | 1,447 of 1,447 |
| `+0x04` `u32` `0x08000604` | 1,445 of 1,447 (a version word; the two exceptions are in `STADATA.DAT`) |
| `+0x08` NUL-terminated ASCII **name**, up to 27 characters | **1,447 of 1,447** printable; 603 of 651 in `STADIUMS.DAT` end in `.smf`, every one in the other two containers does; 583 distinct in `FIELDART`, 616 in `STADIUMS`, 154 in `STADATA` |
| `+0x24` `u32` 104 | 1,447 of 1,447 — the header's size |
| `+0x28..+0x3C` up to six `u32` offsets | four or five non-zero in every non-stub member, **all inside the member**; zero in the 315 stub members of `STADIUMS.DAT` (132 bytes long) |

So a **read-only inventory is derivable with evidence**: each member's own
name, its size, and how many sections its header addresses. The name is what
the Stadiums page needs to list stadiums; the geometry behind the offsets is
not decoded and nothing here pretends it is. `DMF` (324 members) was not
probed.

**Cost.** A `ReadOnlyLane` over the three containers, `read-only-mapped`: an
afternoon. Not built this pass because the Stadiums and Field Art pages are on
the parallel art-pages branch.

**Status: narrowed.** Missing fact for an editor: what the sections are.

---

## 6. Preload-cache semantics

**Root cause.** `GAME.QKL` and `FE.QKL` carry 6,270 byte copies of container
directories and members, every one identical to what it copies [M]. Writers
keep every copy in step or refuse. **Which copy a given screen reads is not
known** [A], and it decides whether a stale copy is harmless, fatal, or
silently wins.

*Two of the 6,270 were unresolved until this pass* [M,
`measured/madden09_ps2/preload-copy-attribution.json`]: `FE.QKL` carries two
rows naming `UIS_FONT.DAT` member 10 of a ten-member container, and
`PreloadCopy.length_in` refused them rather than guess how long they were. The
rows' file index is read correctly — its neighbours with the same index resolve
and match — and both sit at exactly the offset the cache's own header row gives
`UIS_PERS.DAT`, the next file in the `FILS` list, where the 512 bytes are that
container's header byte for byte. So the member number is EA's error, and a
copy is now attributed to the container whose bytes it **is**, with the row's
own words kept beside it. Retail Madden 09: 6,270 copies, **0 refusals**.
Madden 06, where twelve rows alias out-of-range `SOUNDDAT.DAT` numbers onto two
offsets that cache already attributes to real members: **0 refusals**.

**The cheapest experiment.** One texture, drawn on a screen the owner reaches
in under a minute, carried by a cache. `UIS_IG.DAT` member 53, image 0 — a
128×64 8-bit texture — is carried by `GAME.QKL` and was drawn in **all 32**
coin-toss frames of the dump [M]; its derived and dump-confirmed names are in
the identity table. Two builds, each from the retail image:

1. **container only** — the art writer rewrites the member in `UIS_IG.DAT`
   with a recognisable recolour and is told *not* to rewrite the cache copy
   (a one-flag change to the writer, or a hand edit of the built image at the
   declared range);
2. **cache only** — the opposite: the `GAME.QKL` copy carries the recolour,
   the container does not.

Boot each to the coin toss. Four outcomes, each a finding: the recolour shows
in (1) and not (2) — the game reads the container; in (2) and not (1) — the
game reads the cache; in both — the game reads whichever it needs and both
matter; in neither — the texture is drawn from somewhere else and the
identity is wrong. `PLYRFACE.DAT` member 150 (carried by **both** caches,
drawn in six frames) is the second candidate for the front-end cache, and
`UIS_TMLO.DAT` member 1 (a team logo, `GAME.QKL`, one frame) the third. The
report is one line each: *build N: recolour seen / not seen at the coin toss*.

**Status: narrowed** to a two-boot experiment with a named target.

---

## 7. Identity blast radius

**Root cause.** A team's identity lives in three databases; the identity lane
writes two and refuses the third — `TEMPLATE.DAT` member 1 — because
`FE.QKL` names the container [M, `MADDEN09_PS2_IDENTITY.md` §2.2]. Stadium and
city names live only in `TEMPLATE.DAT`'s `STAD` and `CITY` tables [S]; 543
`TEXT` members spell a team's name as prose [M]; `TCDO`/`TCRP`/`TGPT`/`TCTX`
are hypotheses [S].

**What is measured now** [M]. `FE.QKL` carries **one** member of
`TEMPLATE.DAT` — member 11, the user-profile template — and one copy of the
container's directory; `GAME.QKL` carries nothing of it. Member 1, the `TEAM`
copy, is in **neither** cache. A record edit changes no length, so the
directory copy stays valid untouched. **The refusal is over-conservative**:
the third copy can be written with the same bounded path the other two use,
plus one check the caches already make possible — after the build, the
`FE.QKL` directory copy still equals the container's first `data_offset`
bytes, and no member copy of member 1 exists.

**What a consistent rename requires**, lane by lane:

| where | rows | lane | state |
|---|---:|---|---|
| `DB_TEAMS.DAT` members 0..31 `TEAM` | 32 | identity | written |
| `STRMDATA.DB` `TEAM` | 32 | identity | written |
| `TEMPLATE.DAT` member 1 `TEAM` (66 fields) | 32 | identity | **writable; not yet written** |
| `TEMPLATE.DAT` members 2, 3 `STAD` (68 fields), 4/6/12/16 (74) | 50–57 rows [S] | none | a relocation needs it; same path |
| `TEMPLATE.DAT` members 2, 3, 12 `CITY` (17 fields), 4/6/16 (21) | — | none | same |
| `TEXT` banks spelling a name | 543 members | text lane | one slot at a time |
| team logos `UIS_TMLO.DAT`, kits `UNIFORMS.DAT` | 58 + 2,797 identified textures | art lanes | pixels, not names |

**Cost.** The third copy: about 200 lines in `identity_lane.py` mirroring the
`STRMDATA.DB` path, plus the cache-equality check and tests; half a day. A
stadium/city renamer on the same path: a day. Not built this pass.

**Status: narrowed.** Missing fact for the rename: none — it is work. Missing
fact for `TCDO`/`TCRP`/`TGPT`/`TCTX`: a boot with one changed.

---

## 8. Text-lane granularity

**Root cause.** Most text banks are one string per member; `OSDKSTRN.DAT`
carries `KEY=value` pairs the lane offered as one slot per member [M,
`MADDEN09_PS2_MODULE.md` §3.4].

**The grammar, measured** [M, all 13 members, 740,925 bytes]:

| fact | result |
|---|---|
| pairs per member | exactly **1,161** in every member (13 members × 1,161 = 15,093 `=`, 15,080 `\|`) |
| grammar | `KEY=value` pairs separated by `\|`; no NUL inside any member; every part carries an `=` |
| keys | the **same 1,161 keys in all 13 members** — one member per language or variant; 1,160 match `[A-Za-z0-9_]+`, one carries a hyphen; 2 to 28 characters, upper case, digits and underscore |
| values | 0 to over 512 characters (6,744 under 16, 17 over 512); 67 carry a newline; 988 commas and 62 semicolons inside values |

So a **key is a slot**: the member is one string, a value is the run between
`KEY=` and the next `|`, and an edit rewrites the whole member string with the
new value spliced in, NUL-padded to the member's stored length — the same
allocation rule the lane already applies, one level down. A value that would
push the member past its stored length is refused with the byte count.

**Cost.** A `KEY=value` slot kind inside `text_lane.py`, keyed by
`<member>:<key>`: an afternoon, with the verifier re-splitting the destination
member and reading the value back.

**Status: narrowed.** Missing fact: none — it is work.

---

## 9. Roster limits

**Root cause.** `PWGT` and `PHGT` were left off the roster page because their
units were a guess [M, §3.3]; no player can be added because every
`DB_TEAMS.DAT` table is packed full (1,496 of 1,496) [S].

**The units, measured** [M, all 12,265 `PLAY` records of the 235 databases]:

| field | width | values | unit |
|---|---:|---|---|
| `PHGT` | 7 bits | 60..84, mode 75 | **inches** — the executable reads it into the runtime height it compares with 75.0 inches [S] |
| `PWGT` | 8 bits | 0..206 (44 zeros are empty records) | **pounds less 160** — the encoding the sibling Madden 08 roster compiler writes into the same schema and has seen load in PCSX2 [S]; 160..366 lb, against runtime thresholds of 180, 222 and 310 lb in the executable [S] |

Both are offered now, the weight labelled *Weight less 160 (lb)* so the number
written is the number the field holds.

**Player additions** are gap 4's route: a grown `PLAY` table (the schema is
110 fields, 104 bytes, and `PGID` is 15 bits wide — 32,768 is the format's
ceiling [S]) re-packed and relocated, with the depth chart and injury tables
that reference `PGID` left consistent. Offline-provable; one boot to see a
roster screen list the extra row.

**Status: closed** for the units; additions are gap 4.

---

## 10. The container checksum question

**Root cause.** No field in any `TERF` header varies with content across
47,769 members [M]; that is a negative, not a proof [`EA_TERF_FORMAT.md` §6].

**Measured on the Deluxe image** [M]. Thirteen containers differ between the
two discs. In every one of the thirteen, **every byte of the `TERF` chunk
other than the member count is identical to the retail chunk** — the version
word `02 02 00 05`, the alignment, the padding — and the only header fields
that changed are the member count and the `DIR1`/`COMP`/`DATA` chunk sizes
that follow from it. `UIS_FONT.DAT`, the one `HSH1` container, is byte-identical
on both discs. So the rewritten containers carry no word that tracks their
content, and a rebuilt disc that changed every one of them plays [S].

**What closes it.** One boot of any rebuilt container (§14, boot 1). If the
game loads it, the question is closed for that container class; if it refuses,
the checksum lives in the executable or a cache and the search resumes there.

**Status: narrowed** — the negative is now measured on both discs.

---

## 11. Presentation

**Root cause.** The scorebug and overlays are drawn by the executable; no data
file was mapped to them [`game.json` page note].

**What is measured** [M]. `UIS_IG.DAT` — the in-game UI container — holds 67
members, **66 `MMAP` images the derivation names**, 36 of them carried by
`GAME.QKL`. Six of them were identified in the coin-toss dumps, and one
(member 53, 128×64) was drawn in **all 32** coin-toss frames — the overlay
art that screen uses is on the disc, decodable by the uniform decoder, and
nameable for a PCSX2 pack. `UIS_FONT.DAT` holds 10 `FNTS` members, 3 carried
by `FE.QKL` and 1 by `GAME.QKL`, with no decoder here. What the executable
draws is the *layout* and the *numbers*; what it draws them with is `UIS_IG`
textures and `FNTS` glyphs.

**What an honest page could edit.** The `UIS_IG.DAT` textures, through the
art lanes (the pack route once §14's boot 3 has run; the disc route today).
The `FNTS` format is the missing piece for text; a probe of its header is an
afternoon.

**Status: narrowed.** The art-pages branch owns the page; the page note
should say the overlay art is `UIS_IG.DAT`.

---

## 12. Deluxe

**Root cause.** Writers and evidence were retail-only; the Deluxe executable
differs in nine words and thirteen `/DATA` files [M].

**Measured: every lane cataloguing the Deluxe image** [M]:

| lane | Deluxe result | works unchanged? |
|---|---|---|
| inventory | 100 containers, 34,600 members | yes |
| team databases | 355 databases, 340,806 records, **12,550** editable rows; no cache names `DB_TEAMS.DAT` | yes |
| text | 14,760 banks, 17,822 strings; **no container refused** — the Deluxe disc has no `QKL` caches, so `GAMEDATA`/`LOADDATA`/`STADATA` are editable there | yes, wider |
| identity | 32 teams, 64 copies per build | yes |
| executable patches | edition `deluxe`, CRC `084562FF`, all 5 sites match | yes |
| audio | 34,056 streams, 297 decodable (`BGM.DAT` 57 streams, 55 decodable); banks unchanged | yes |
| uniform art (both rows) | **`UNIFORMS.DAT` (137 MB) and `STADIUMS.DAT` (161 MB) exceed the 96 MB read limit** and are skipped — the catalogue now says why instead of "could not be opened"; faces and tattoos (1,325 members) catalogue | partly |

So every lane *catalogues* it; the one catalogue refusal is a size limit, not a
format.

**The database writers used to refuse it** [M, the witness-disc builds]. Both
`team_data` and `identity` refused the Deluxe image with one sentence: the
container's directory record says 2,559,112 bytes and the container "carries"
2,585,280, and a rewrite that grows a file is not one they do. The text lane
and the executable patches built and verified on the same image. What is
behind that sentence, measured on every `/DATA` container of the Deluxe disc:

| fact | result |
|---|---|
| containers whose `DATA` chunk declares more than the directory record | **9** (none on the retail disc): `BGM` +1,164, `DB_TEAMS` +26,168, `FIELDART` +18, `MOVIEDAT` +632, `STADIUMS` +48,304, `TEMPLATE` +60, `UIS_PLYR` +4, `UIS_STAD` +4,052, `UNIFORMS` +21 bytes |
| of the 9, the declared length still fits the record's own last sector | 5 (`BGM`, `FIELDART`, `TEMPLATE`, `UIS_PLYR`, `UNIFORMS`) — every member inside the recorded extent |
| of the 9, the declared length needs sectors past the record | 4 (`DB_TEAMS` 13, `STADIUMS` 24, `UIS_STAD` 2, `MOVIEDAT` 0 rounded) |
| in those 4, what lies past the record | **only trailing empty members** — 409 of `DB_TEAMS`'s 644, 755 of `STADIUMS`'s 2,120, 64 of `UIS_STAD`'s 115, all 10 of `MOVIEDAT`'s — each owed one 64-byte alignment unit the repack tool did not write; **no non-empty member ends past the record in any of the 9** |
| sectors between each record's end and the next file | **0** in all 4 — the next file starts in the very next sector |

So the Deluxe rebuild's `DATA` size is overstated by the trailing empty
members' padding, the bytes past the record are the **next file's**, and the
reader's recovery to the declared length reads a neighbour's head as this
container's tail (harmless, since only empty members live there, and a defect
all the same). The writers then compare the recovered length with the record
and refuse.

**What closed it, bounded, without growth** [M]. The reader still recovers to
the declared length — that is right for a reader, and it is how the catalogue
sees every member — but a **writer** now takes the other view. One shared
preflight, `containers.open_for_rewrite`, hands a lane exactly the ISO9660
record's bytes, says whether the container is one of the recorded-short ones,
and refuses — naming the recorded size **and** the declared one — when a member
with bytes really does lie past the record, or when a recipe names one.
Underneath it, `ea_terf.rewrite_member` and `plan_member_rewrite` take an
`allow_short_tail` recovery mode: the `DATA` chunk's declared size is written
back exactly as the disc had it, the result is the same length as the input, no
member may move, and an empty member's slot past the record is left alone. So
the rewrite lands inside the recorded extent, the directory record never
changes, the bounded ISO write is untouched, and the same verifier applies.
`layout_violations(allow_short_tail=True)` forgives exactly one departure — a
`DATA` chunk short of the layout rule's end with only empty members in the
difference — and nothing else.

**Proof on the Deluxe image** [M,
`measured/madden09_ps2/deluxe-recorded-short-writers.json`], using the two
recipes that produced the old sentence:

| | |
|---|---|
| `disc4-01-roster.json` through `players_rosters.team_databases` | **PASS** — 3 values read back from the destination, 1 database re-parsed with 44 checksum slots all correct, **0 undeclared changed bytes** |
| `disc4-02-identity.json` through `colors.team_identity` | **PASS** — 8 values read back, 2 databases re-parsed with 470 checksum slots all correct, **0 undeclared changed bytes** |
| image bytes, before and after | 1,846,476,800 → 1,846,476,800 |
| directory records moved or resized | **0 of 109** |
| `DB_TEAMS.DAT` recorded length, before and after | 2,559,112 → 2,559,112 |
| its `DATA` chunk's declared size, before and after | 2,574,848 → 2,574,848 |
| its container directory (header + `DIR1`), before and after | **identical** |
| bytes of it that differ (identity build) | **10**, all inside the edited record's span |

And the refusal that must survive: a recipe naming member 235 — the first
member whose slot starts past the record, and empty like the other 408 — is
still refused, with both sizes in the sentence: *"/DATA/DB_TEAMS.DAT member 235
ends at byte 2,559,168, and this image's own directory records the container as
2,559,112 bytes against the 2,585,280 it declares; rewriting a member out there
would have to grow the file, which this lane will not do."*

The fixture is built from the format's rules, not from a disc:
`containers.make_recorded_short` does to a synthetic container what the Deluxe
repack tool did to its own, and `build_synthetic_disc(recorded_short=True)`
puts one on the synthetic disc, so CI proves the recovery mode with no game
data.

**Cost of the other refusal.** Lift the art lane's read limit for containers
it walks member by member (the audio lane already maps large containers) —
half a day. Not done this pass.

**Status: narrowed.** The recorded-short half is **closed** — both database
lanes build and verify on the Deluxe image. What is still open: the two art
containers over the 96 MB read limit, and a Deluxe boot of any rebuilt
container (§14 boot 8, which can now include boot 1's line).

---

## 13. `MMAP` palette banks, LZH1 worst case, ISO free space

**Palette banks.** The five `STADIUMS.DAT` members the decoder excludes are
not a pixel format: they are **palette-only members** — `surfaceCount 0`,
45 alternate 256-entry CLUTs each — and `UNIFORMS.DAT` has one more [M].
They are what a team recolour is; the `MMAP` writer already rewrites a
palette, so a CLUT editor over them is the missing page control, not a
decoder. `GAMEDATA.DAT` carries four surfaces of pixel layout 4 at exactly
4 bytes per texel — 32-bit direct colour [M], decodable without a palette;
not done this pass.

**LZH1 worst case.** 1.96× is the ratio on tiny members where the 158-byte
code-length table dominates [M, `EA_TERF_FORMAT.md` §5.3]. It is moot for the
writer: `plan_member_rewrite` prices stored against compressed and takes the
smaller, and a stored member inside a `COMP` container is a shape the retail
disc ships 959 times [M]. No member is ever written at 1.96×.

**ISO free space.** The writer relocates a grown container only on request
and appends; it does not search the image for a gap. The retail image leaves
21,997,568 bytes unaccounted for by any file [S] — seek padding — which a
search over the sorted extent map would find in milliseconds. Cost: an
afternoon in `tools/ps2_iso9660_writer.py`, with the verifier's "no untouched
extent moved" rule unchanged.

**Status: narrowed** on all three; none blocks a lane.

---

## 15. The uniform verifier and a recipe naming several images of one member

**Root cause** [M, the witness-disc builds]. A recipe naming nine textures,
five of them different images of one `UNIFORMS.DAT` member, planned and built
cleanly — nine of nine pixel-exact — and the lane's own verifier then refused
it: *image 1 of member 11 changed and no edit named it*.
`_check_one_texture` held every image of an edited member other than the
row's own to be unchanged, so the second edit of the same member looked like
an intrusion to the first. A defect in the verifier, not the writer; a
single-image recipe never met it.

**Fixed.** The verifier exempts the set of images the receipt names for that
member, as a whole, and every image nobody named must still be the picture it
was. `containers.synthetic_mmap` grew an `images=` option so the fixture can
carry two drawable images of one member, and the regression test builds both,
verifies PASS, and shows the unexempted check still refusing the sibling.

**Status: closed.**

---

## 14. Nothing has been booted — the witness plan

Every writer is `offline-writer-proved`; the rung above needs a screen. The
owner runs these in order, one rebuilt disc per writer, retail image first.
Each line to report is one sentence. Boots 1 and 3 also settle gaps 10 and 6;
boot 8 settles gap 12.

1. **Team databases** (`compile` a `DB_TEAMS.DAT` rename of one player on one
   team). Look at: Team Management → that roster. Report: *the new name is /
   is not on the roster*. Settles gap 10 for a `DATA` container.
2. **Text banks** (one `OSDKSTRN.DAT` slot). Look at: the online/front-end
   screen the slot belongs to. Report: *the replaced string is / is not on
   screen*.
3. **Uniform art, container only** (§6 build 1: `UIS_IG.DAT` member 53
   recoloured, cache copy left stale). Look at: the coin toss. Report:
   *recolour seen / not seen*. Settles gap 10 for a `COMP` container and half
   of gap 6. A kit texture recoloured on the same disc earns a second line:
   **which team's jersey changed**. No uniform texture yet attributes to one
   team — the same members attribute identically to both teams of a matchup
   (the dumped coin-toss frames each show one team in colour and one in white,
   and the identity table records which is which per frame) — so that line is
   new information for the identity table, not a check of it.
4. **Uniform art, cache only** (§6 build 2). Same screen. Report the same
   line. Settles gap 6.
5. **Identity** (one team's abbreviation and primary colour). Look at: Team
   Select, then the helmet preview. Report: *abbreviation new / old; colour new
   / old*; note whether any screen still shows the old name (the `TEMPLATE.DAT`
   copy, gap 7).
6. **Audio stream** (one `BGM.DAT` track replaced by a tone). Look at: the
   front end with music on. Report: *tone heard / original heard*.
7. **Executable patch** (the four-cap pnach). Look at: create-a-playbook, add a
   twenty-first set to a shipped 20-set book. Report: *the editor's message, or
   the set added*. Then the same with a grown book when gap 4's writer exists.
8. **Deluxe** — the text lane and the executable patch already build on the
   Deluxe image (§12); boot that disc and report boot 2's line and boot 7's.
   The database lanes cannot build on it until §12's recorded-short fix
   lands; then repeat boot 1 there. Boot 3 repeated on Deluxe settles art
   once the read limit is lifted.
9. **PCSX2 pack** — a folder of one derived-name PNG for the boot-3 texture,
   `LoadTextureReplacements` on, stock disc. Look at: the coin toss. Report:
   *replacement drawn / not drawn*. This is the one boot that moves gap 1's
   pack step.

Order matters only in that 1 and 3 answer the checksum question before anything
else is judged: a refusal to load at boot 1 makes every later "not seen" a
loading failure, not a lane failure.
