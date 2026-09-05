# Phase 2 — PS2 on-disc text

Status: **built and proved on the retail disc**, 2026-09-04. Bounded,
fixed-allocation editing of ESPN NFL 2K5's PlayStation 2 text banks
(`SLUS-20919`), riding the ISO9660 writer.

The plan called this "2–3 days, optimistic — 716 disc banks ≠ one ROST arena."
The first job was to make that honest. It turned out to be optimistic and
pessimistic at once, for reasons neither the plan nor the Xbox side had written
down. What follows is what the disc actually says.

## 1. The 716 was never 716 editable banks — on either platform

`PS2_PORT_HANDOFF.md` reads "Xbox edits 20,074 strings across 716 banks", which
invites the reading that 716 banks must be ported. They must not.
`UNIVERSAL_TEXT_AND_25TH_FINDINGS.md` breaks the same 716 down, and the
breakdown is the answer:

| kind | banks | what it is | in scope? |
|---|---:|---|---|
| `NAME` | 635 | 160-byte player-name-atlas **metric** tables — one object label, then 29 pairs of 16-bit atlas offsets and advances | no — not user text |
| `ROST` | 76 | roster identity, owned by the bounded roster writer | no — another lane |
| `STRG` | 2 | the string tables | **yes** |
| `CRED` | 1 | credits | **yes** |
| `SITU` | 1 | ESPN 25th Anniversary moments | **yes** |
| `TRIV` | 1 | trivia questions | **yes** |

So the fixed-allocation text surface is **five banks**, on Xbox and on PS2
alike. 20,074 is Xbox's editable-string count *including* 13,416 ROST strings;
strip those and Xbox exposes 6,658 editable strings across these four kinds.

## 2. Bank parity: exact

Counted straight out of the two disc inventories (`inventory_ps2.tsv.gz`,
`inventory_xbox.tsv.gz`), by FourCC:

| kind | PS2 | Xbox |
|---|---:|---:|
| `CRED` | 1 | 1 |
| `NAME` | 635 | 635 |
| `ROST` | 76 | 76 |
| `SITU` | 1 | 1 |
| `STRG` | 2 | 2 |
| `TRIV` | 1 | 1 |
| **total** | **716** | **716** |

And the five in-scope banks are not merely the same *count* — they are the same
banks. Same resource ids, same stored sizes, same record counts, same descriptor
offsets:

| bank | PS2 size | Xbox size | resource id | records | descriptor |
|---|---:|---:|---|---:|---|
| `CRED` | 29,856 | 29,856 | `0x261bb728` | 619 | `0x30` |
| `SITU` | 29,104 | 29,104 | `0x3f407cf4` | 25 | `0x40` |
| `STRG` (main) | 160,432 | 160,432 | `0xc59d46a8` | 1,492 | `0x30` |
| `STRG` (small) | 6,080 | 6,080 | `0xc61a9833` | 9 | `0x30` |
| `TRIV` | 242,848 | 242,848 | `0x5a14cf27` | 691 | `0x44` |

Parsing them yields **6,873 strings, 6,658 editable, 215 read-only** — digit for
digit the Xbox numbers for these kinds (STRG 1,113 + SITU 100 + CRED 608 +
TRIV 4,837 = 6,658; read-only STRG 2 + SITU 50 + CRED 163 = 215). Every Xbox
layout constant transferred unchanged and is re-checked against the PS2 bytes on
every run rather than assumed.

## 3. Encoding: UTF-16LE, measured

Both machines are little-endian and both builds store these pools as
NUL-terminated UTF-16LE. Measured per bank, not inferred: each object's own name
pointer decodes as UTF-16LE (`credits`, `situation_data`, `strings`,
`trivia_questions`), and every pool allocation decodes cleanly. A bank whose
pool does not decode as UTF-16LE is refused rather than guessed at.

So a character costs two bytes on PS2 exactly as on Xbox, and the Xbox character
budgets transfer with no arithmetic change. The concern that "UTF-16 halves the
character budget" relative to ASCII does not arise as a *difference* — both
platforms were already paying it.

Two further measurements, both from all 6,873 strings:

* **The corpus is plain ASCII.** Not one character above U+007E. 45 line feeds
  and one carriage return do occur, so a multi-line replacement is legitimate.
* **Formatted tokens are pipe-delimited, not printf.** Two strings carry
  `|LINK|` / `|M_ADVANCE|` markers, from the 57-entry inline-token table
  `tools/nfl_formatted_token.py` recovered. **Zero strings carry a printf
  conversion.** Twelve trivia answers end in a literal `%` ("20%"), which a
  loose `%`-matcher would have mistaken for one — so the conversion pattern
  requires an actual conversion character after the `%`, and those twelve
  correctly match nothing.

## 4. The finding that changes the shape of the feature: zero slack

**No allocation on this disc has spare room.** Across all 6,873 strings, an
allocation is exactly `len(text) * 2 + 2` bytes. The pools are packed end to end
with no padding anywhere.

That means the character budget is *not* "the allocation minus what is used" —
it is **the original string's own length**. A replacement may be shorter or
exactly as long. One character longer is refused, and there is no string
anywhere on the disc with even one spare code unit to soften that.

This is the single most consequential fact about the surface, it is not written
down on the Xbox side, and it was not visible from the plan. Any UI built on
this must show the budget as the original's length and must not imply that
headroom exists.

## 5. Two things that did *not* have to be built

* **No VC-LZ recompression.** Every text bank is stored uncompressed — chunk
  magic `0`, not `0xFEEDBEEF`. The "recompress to fit the fixed span or refuse"
  requirement is therefore a refusal the writer states and never has to
  exercise. Carrying an unexercised recompression path would have been worse
  than refusing, so the patcher refuses a compressed bank outright and says why.
  If a disc revision ever compresses one, that refusal is the correct answer
  until the path exists and is proved.
* **No multi-pack handling.** All five banks live entirely inside
  `/VC_20919/0.`, so one bounded ISO9660 file replacement covers any edit. A
  bank that straddled two packs is detected and refused.

## 6. Safety: what is claimed, and where it stops

A string is listed editable only when all of these hold, derived from the disc:

1. the whole resource body **rebuilds byte-identically** from the decoded
   structure — every pointer, count, id and pool boundary re-serialized and
   compared, so nothing is carried across as an unexamined blob;
2. its allocation is a NUL-terminated UTF-16LE run starting on a pool-entry
   boundary, not inside a longer string;
3. the allocation has room for at least one code unit past its terminator;
4. its consumer is display copy, not lookup or scenario logic.

Rule 4 is the Xbox safety argument and it transfers intact: `SITU`'s two
team-resource selectors stay read-only because scenario lookup consumes them,
and `TRIV`'s numeric correct-answer key is never touched while its seven display
fields open up. Read-only outcomes by kind: CRED 163 zero-capacity allocations,
SITU 50 selectors, STRG 2 zero-capacity allocations.

**Aliasing is reported, never hidden.** 281 allocations are referenced by more
than one lookup record, 279 of them editable, the most-shared editable one by 18
records — so editing it changes all 18. (The single most-referenced allocation,
at 468 references, is CRED's zero-capacity empty string, which is read-only
anyway.) The catalog carries a reference count per allocation for exactly this
reason, and a UI must show "used by N records" rather than pretending aliases
are independent strings.

**One honest gap.** The small `STRG` bank ends in four bytes past its pool whose
meaning is not proved (the main bank's 12 and the other trailers are zeros).
They are preserved verbatim, digested and reported as opaque. No string
allocation overlaps them, so a bounded edit cannot reach them — but the catalog
says "opaque", not "padding", because only one of those is known to be true.

## 7. What shipped

| file | role |
|---|---|
| `tools/nfl2k5_ps2_text_target_catalog.py` | walks the ISO read-only, finds and decodes the banks, emits the catalog |
| `reports/gameplay_tuning/nfl2k5_ps2_text_target_catalog.v1.json` | 5 banks, 6,873 strings — names, offsets, allocation sizes, code-unit counts, reference counts, token shapes, SHA-256 digests, **no decoded text** |
| `tools/nfl2k5_ps2_text_patch.py` | recipe → new ISO via `ps2_iso9660_writer.replace_files` |
| `tools/nfl2k5_ps2_text_verify.py` | independent re-derivation from source + output + recipe |
| `tools/validate_nfl2k5_ps2_text.{sh,bat}` | deterministic validators, no game data |
| `tests/mod_editor/test_nfl2k5_ps2_text.py` | 34 tests on synthetic images |
| `reports/gameplay_tuning/nfl2k5_ps2_text_trial.v1.json` | the real-disc trial record |

The verifier imports neither the patcher, the catalog, nor the ISO writer's
reader, and derives the pool in the opposite order — pointer-first, where the
catalog scans the pool forward. Two derivations that agree are evidence; one
derivation quoted twice is not.

Its decisive check is a **full byte comparison of both 4.3 GiB images**: the
differing set must be exactly the bytes the recipe's allocations should have
changed, not a subset and not a superset. That check has to exist here because
the ISO-level verifier cannot supply it — the writer replaces whole *files*, so
it declares the entire 1 GiB pack extent as written and cannot distinguish a
stray byte inside it from an intended one.

**Cost.** Because the ISO writer replaces whole files, one run streams the 1 GiB
pack to a temporary file, patches a handful of bytes, then copies the 4.3 GiB
image: ~5.5 GiB of I/O to change 13 bytes, about 7½ minutes here. That is the
price of reusing the bounded writer instead of reaching into the image directly,
and it is the right trade.

## 8. Real-disc trial — on a copy

Two franchise training-regimen menu labels in the main `STRG` bank, both single
reference and token-free. One replaced with a same-length string (the tightest
case, given zero slack), one with a shorter string so the zero-filled tail was
exercised. Full record in `nfl2k5_ps2_text_trial.v1.json`; strings are
identified by bank, pool index and digest, never by their text.

| | |
|---|---|
| source | 4,665,081,856 bytes, `f1300699ab445ad0…`, serial `SLUS-20919`, volume id `50137` |
| source after the run | unchanged, re-hashed |
| output | 4,665,081,856 bytes, `278fe57323086a8c…` — same size, never committed |
| edit 1 | pool index 905, allocation 10 bytes, 4 → 4 code units, 4 bytes changed |
| edit 2 | pool index 1105, allocation 20 bytes, 9 → 8 code units, 9 bytes changed |
| bytes changed | **13**, in 13 one-byte runs — UTF-16LE leaves the zero high byte of a replaced ASCII character alone |
| `nfl2k5_ps2_text_verify` | **pass** — 12 checks, patch report agrees |
| `ps2_iso9660_verify` | **PASS** — 79 entries compared, 3,591,340,024 unchanged bytes compared |

**The trial earned its keep by finding a bug the synthetic tests had missed.**
The last allocation in a pool has no following pointer to bound it, so a
verifier that derives allocation ends from the destination alone reads a
shortened *final* string as "the pool shrank" and fails a perfectly legal edit.
The source's boundaries settle it, and the destination is now checked against
them — a stronger check, not a weaker one. A test covers that case directly now.
The synthetic bank had simply never shortened its last string.

**No emulator.** This proves the bytes; it does not prove the label renders. A
PCSX2 spot check belongs to the runtime lane.

## 9. Honest effort against "2–3 days"

The estimate was **roughly right on the total and wrong on every line item**.

What made it *cheaper* than budgeted:

* The Xbox result did not need porting so much as re-checking. Every layout
  constant — descriptor offsets, record counts, record strides, pointer bias —
  held exactly, so the parsers were a rewrite against known shapes rather than
  reverse engineering. Parity that exact was a real possibility, not a given,
  and finding it early is what made the rest cheap.
* Nothing was compressed and nothing straddled a pack, deleting two whole
  workstreams the brief had allowed for.
* `replace_files` and `ps2_iso9660_verify` were ready and correct. The ISO layer
  cost nothing but I/O time.

What made it *more expensive* than budgeted:

* The zero-slack finding is not in any prior document and changes what the
  feature can promise. Establishing it meant measuring all 6,873 allocations.
* The independent verifier is most of the work, and it is the part the estimate
  did not price. It needs its own ISO walk, pack walk, chunk walk, VC pointer
  decode and pool decode, in a *different* derivation order, plus a whole-image
  comparison — because the ISO verifier provably cannot cover the inside of a
  declared extent.
* The 7½-minute write / 2½-minute verify loop makes each real-disc iteration
  expensive, which is why the synthetic suite had to be good first.

Net: **about a day of concentrated work**, inside the 2–3 day estimate, but
arrived at by a different route than the estimate imagined. The plan's stated
worry — "716 disc banks ≠ one ROST arena" — was the wrong thing to worry about;
716 was never the workload. The right worry, unstated, was that the editing
surface has no headroom at all.

## 10. Biggest remaining unknown

**Nothing has been seen on a screen.** Every claim here is about bytes:
allocations, pointers, digests, ranges. The safety argument for rule 4 —
"display copy, not lookup" — is inherited from the Xbox analysis rather than
re-derived against the PS2 ELF, and no PS2 string has been observed rendering
after an edit. Two specific risks sit behind that:

1. **A width or layout consumer.** A menu that lays out from a measured string
   width will re-flow when a label shortens. Byte-safe is not the same as
   visually correct, and the 45 embedded line feeds hint that at least some of
   this text is laid out rather than simply drawn.
2. **A length-dependent consumer we cannot see.** The Xbox argument covers the
   consumers Xbox proved. If PS2 code reads any of these strings for comparison
   rather than display, an edit changes behaviour, not just pixels. The
   read-only `SITU` selectors are the known case; there is no proof there is not
   another.

One PCSX2 spot check of the trial image would retire most of this, and it is the
obvious next step for the runtime lane.

## Integration note

`tools/ps2_iso9660_writer.py` and `tools/ps2_iso9660_verify.py` are runtime
dependencies of the patcher and verifier and **must be added to
`packaging/release-allowlist.txt`** in the integration commit. They are not
appended on this branch because the stadium lane needs the same two files and a
duplicate entry would be the result. Registry rows are likewise left to the
serialized integration commit.
