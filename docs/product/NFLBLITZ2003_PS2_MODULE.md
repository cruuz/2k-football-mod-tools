# NFL Blitz 2003 (PlayStation 2) — the module

**What this document is.** `mod_editor/games/nflblitz2003_ps2/` is the sixth game
on the Game Studio shell and the second Midway title. It is the NFL Blitz 2002
module with this disc's identity, this disc's archive names and this disc's
counts — because the two discs' formats are identical in every respect this
project measured, and §2 is that claim with the numbers behind it.
`docs/product/NFLBLITZ2002_PS2_MODULE.md` is the full account of the formats,
the probes, the GS layout measurement and the real-disc trial; this document
carries only what differs.

**Evidence tags.** **[M]** measured on the retail SLUS-20474 disc this box
holds, read-only; **[S]** sourced; **[A]** assumed.

**Retail-free.** Counts, names, offsets, lengths and digests. No line, name,
pixel, palette entry or record from the disc is in this repository.

---

## 1. The verdict, in four sentences

1. **All fourteen pages are answered**, with the same lane set and the same
   classifications as the 2002 module (§3): four writers at
   `offline-writer-proved`, two export lanes at `extract-only`, two inventories
   at `read-only-mapped`, five page notes.
2. **The two discs' formats are identical** in every measured respect but three,
   and all three are data, not shape (§2).
3. **Every gate is green on this disc's own numbers**: 296 of 296 conformance
   checks, five validators, 24 lane tests, and the shared readers' 31 tests.
4. **The writers are proved on this retail disc too** (§4), and every build
   declares **two** ranges where the 2002 disc declares four — the shape
   difference showing up in a receipt. **No image has been booted.**

## 2. What differs from NFL Blitz 2002, in numbers [M]

Three things, and nothing else the readers can see:

| | NFL Blitz 2002 | NFL Blitz 2003 |
|---|---|---|
| serial / boot ELF | SLUS-20051 / `SLUS_200.51`, 2,342,232 B | SLUS-20474 / `SLUS_204.74`, 2,417,112 B |
| image | 1,464,205,312 B, 36 files | 1,029,144,576 B, 22 files |
| the pair | `/DATA/BASSETS.ZIP` + `.ZIH` | `/DATA/BERTHA.ZIP` + `.ZIH` |
| **`.ZIH` record shape** | **inline** — nine `u32` then the name, **with a CRC-32 column** | **table** — `u32` name offset, size, data offset, then one string table, **no CRC column** |
| members | 2,426 | 2,695 |

Everything else holds on both, exhaustively:

| identity | 2002 | 2003 |
|---|---|---|
| `body bytes + 8 == the .ZIH file` | holds | holds |
| the index walk consumes the file to its last byte | holds | holds |
| index names equal the archive's, as sets | 2,426 | 2,695 |
| index sizes equal the central directory's | 2,426 of 2,426 | 2,695 of 2,695 |
| index offsets equal the archive's own local-data offsets | 2,426 of 2,426 | 2,695 of 2,695 |
| every member's compression method is *stored* | 2,426 | 2,695 |
| local-header extra field empty | 2,426 | 2,695 |
| index order is by name; archive order is by data offset | both | both |
| index CRC column equals the central directory's | 2,426 of 2,426 | **no column** |
| recomputed CRC-32 over the stored bytes agrees | 600 of 600 | no column |
| `.rtd` whose one section accounts for the file | 761 of 761 | 840 of 840 |
| rasters read (= the count each dictionary declares) | 10,420 | 11,828 |
| rasters whose TEX0 agrees with the header's w/h/depth | 10,420 | 11,828 |
| platform word `PS2\0`; library version `0x0401ffff` | all | all |
| `roster.rst` bytes / `% 1,804` / blocks | 73,964 / 0 / 41 | 75,768 / 0 / 42 |
| blocks whose header word is 18 | 41 of 41 | 42 of 42 |
| records whose byte +68 equals their block ordinal | 738 of 738 | 756 of 756 |
| `CPTH`: `16 + records * 32 == the member` | 85 of 85 | 88 of 88 |
| `WIFF`: big-endian size + 8 == the member | 190 of 190 | 209 of 209 |
| `.dff` walk consumes the member | 1,043 of 1,272 | 1,167 of 1,436 |
| `.trv`: `size % 40 == 0` | 40 of 40 | 40 of 40 |
| `.ini` / `.tab` / `.txt` printable ASCII, CRLF | 32 of 32 | 34 of 34 |

**The one shape difference is the index's record layout, and the readers already
tell the two apart from the bytes** — the table shape is recognised because its
first record's first word is the directory's own length, `entries × 12` [M]. So
the writer's three-place rule becomes a two-place rule on this disc, decided by
the file rather than by the disc's name: `plan_member_replacement` returns an
index range only where the index carries a CRC column, and never invents one.

**The team count moved, and the roster moved with it.** The 2003 disc adds one
`<two letters>_crowd.ini` and one `<two letters>_glogo.rtd` — both `ht`, the
Houston Texans, the team the NFL added for the 2002 season — and `roster.rst`
gains exactly one 1,804-byte block [M]. That is the cross-check the roster's
block arithmetic earns, and it is the same on both discs.

## 3. The fourteen pages

Identical to the 2002 module's table, with this disc's counts: 32 crowd tables
rather than 31, 610 team-prefixed dictionaries rather than 594 and 230 others rather than 167, 42 roster blocks and 756 records rather than 41 and 738, 88
camera paths, 209 `WIFF` containers, 1,436 clumps, and a 41st text member,
`credits.txt`, which joins the trivia row because it is CRLF ASCII like the
rest. See `docs/product/NFLBLITZ2002_PS2_MODULE.md` §3 for what each row writes
and `docs/product/measured/nflblitz2003_ps2/` for this disc's numbers.

The boot executable, for the record [M]: `SLUS_204.74`, 2,417,112 bytes, sha256
`57cba3a8…771039a0`, PCSX2 CRC `49A00204`. No patch site on it has been located
by this project.

## 4. What is proved, and what is not

**Proved on the synthetic disc**, which this module builds with the *table*
index shape so the shape difference is exercised in CI rather than asserted:
296 of 296 conformance checks, all five validators, and 24 lane tests including
a round trip through both index shapes.

**Measured on the retail disc**: every identity in §2, produced by the shipped
lanes and recorded in `docs/product/measured/nflblitz2003_ps2/`.

**Proved on the retail disc**: four chained builds on the owner's own
SLUS-20474 image, read-only source, scratch destinations, each verified against
its own source, every image deleted afterwards
(`docs/product/measured/nflblitz2003_ps2/writer-trial.json`).

| step | lane | declared ranges / bytes | verdict |
|---|---|---:|---|
| 1 | `identity.crowd_tables` | 2 / 439,045,798 | PASS |
| 2 | `gameplay.field_table` | 2 / 439,045,798 | PASS |
| 3 | `playbooks.trivia_banks` | 2 / 439,045,798 | PASS |
| 4 | `rosters.player_names` | 2 / 439,045,798 | PASS |

Every destination is 1,029,144,576 bytes, the length of the source, and the
verifier found all 2,695 members present at their original offsets and lengths
with 2,694 byte-identical by streaming digest at every step.

**Two ranges, where the 2002 disc declares four.** That is the whole shape
difference showing up in a receipt: this index carries no CRC-32 column, so a
build rewrites the ZIP and never touches the `.ZIH`. The three-place rule
collapses to two because the index's own record shape says it should, not
because the module knows which disc it is looking at.

**Not booted.** No image built by this module has been booted in an emulator or
on hardware, and no receipt claims otherwise.

## 5. This is an instantiation, not a copy

It **was** a copy. The contract forbids a game package importing a sibling game
(`mod_editor/games/contract.py`, `ALLOWED_CORE_IMPORTS`), and when this module
shipped, the shared layer a second instantiation would use —
`mod_editor/games/_lanes/` — held nothing for a Midway disc. So the lane files
were the 2002 module's with a recorded substitution list applied, and this
section asked the next agent to extract them.

**That extraction is done.** `mod_editor/games/_lanes/blitz_zip_lanes.py` now
holds `TextLineLane`, `RosterNameLane`, `TextureDictionaryLane`,
`ContainerInventoryLane`, the `zip_lane` build/verify pair and the four
command-line entry points, parameterised on a disc-access module exactly as
`_lanes/terf_art.py` is for the two Tiburon discs. Both games are thin wirings
over it: each lane file names which members, which page, which classification
and its own schema string, and nothing else.

| | before | after |
|---|---:|---:|
| `mod_editor/games/nflblitz2002_ps2/*.py` | 2,223 | 1,017 |
| `mod_editor/games/nflblitz2003_ps2/*.py` | 2,224 | 1,018 |
| `mod_editor/games/_lanes/blitz_zip_lanes.py` | — | 1,347 |
| **total** | **4,447** | **3,382** |

A game still never imports a sibling game; both import the shared layer. The
two format readers under `mod_editor/games/_formats/` were already shared and
are unchanged.

The schema strings stay per game on purpose — `nflblitz2003_ps2_text_lines/v1`
is not `nflblitz2002_ps2_text_lines/v1` — so a recipe written against one disc
is refused by the other rather than silently applied to it.

Both formats now have a document of their own:
`docs/product/MIDWAY_ZIP_FORMAT.md` (the pair, both `.ZIH` shapes and **why this
disc's builds declare two ranges where the 2002 disc's declare four**) and
`docs/product/RENDERWARE_TXD_FORMAT.md` (the texture dictionaries, the GS layout
measurement, and a cross-disc census of what the same reader makes of NFL Blitz
Pro, Blitz: The League and Madden NFL 06).
