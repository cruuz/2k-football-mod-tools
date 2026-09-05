# PS2 Phase 2 — uniform colours and the disc roster

The [capability triage](PS2_PORT_HANDOFF.md#capability-triage-wp3-2026-09-04)
picked these two surfaces out of Phase 2 for one reason: their chunk families
are **byte-size-identical across the Xbox and PS2 discs** — 634 `Unif`
resources on each, 76 `ROST` resources on each — and neither is a texture, so
PCSX2 cannot overlay them. They are the cheapest on-disc wins in the registry
and they both ride the ISO9660 writer that already exists.

The triage was careful to say that identical size is **evidence of** a shared
layout, not proof of one, and that every Phase-2 row must confirm the layout
against the real PS2 bytes. This document is that confirmation, plus the two
writers built on it.

Everything below is measured from a user's own `SLUS-20919` image. No disc
bytes, chunks or trial images are committed anywhere.

---

## 1. Parity verdicts

### `Unif` — full parity, 634 of 634

Each uniform package is one outer archive entry whose **chunk 0** is the `Unif`
resource. Read off the retail disc:

```
+0x00  'Unif'                      chunk FourCC
+0x04  u32  stored_size  = 80      (all 634)
+0x08  u32  system_bytes = 0
+0x0C  u32  video_bytes  = 0
+0x10  u32  lz sentinel   = 0      (0xFEEDBEEF would mean compressed)
+0x20  object base, 80 bytes
+0x2C  'Unif'                      object FourCC   (object +0x0C)
+0x30  rel ptr +17  -> +0x40       object name     (object +0x10)
+0x34  rel ptr +29  -> +0x50       descriptor      (object +0x14)
+0x40  UTF-16LE "uniform\0"
+0x50  u32 LE facemask   ARGB      descriptor +0x00
+0x54  u32 LE turtleneck ARGB      descriptor +0x04
+0x60  f32 1.0
```

| measurement | result |
|---|---|
| `Unif` chunks found | **634** |
| stored size | **80 on every one** |
| object tag at chunk `+0x2C` | 634 / 634 |
| UTF-16LE `"uniform"` at chunk `+0x40` | 634 / 634 |
| colour offset resolved through the descriptor pointer | **634 / 634 land on `0x50`** — the Xbox writer's constant |
| LZ-compressed bodies | **0 / 634** |
| distinct colour pairs | 95 |
| targets spanning `/VC_20919/0.` / `1.` | 133 / 501 |

Two further parity facts worth stating plainly:

* **The Xbox writer's header probe already works here byte for byte.**
  `nfl2k5_unif_color_writer.py` checks `probe.startswith(b"UnifP")`. That is not
  a package tag — it is the FourCC `Unif` followed by the little-endian stored
  size `0x00000050`, whose first byte is `0x50` = `'P'`. The PS2 chunk produces
  exactly the same five bytes.
* **The selector namespace is shared.** Each package is keyed by CRC-32 of its
  uppercased UTF-16LE name (XBE `0x38650`). Reversing that over the logical
  namespace maps **all 634 PS2 entries** to Xbox-style selectors —
  **317 HOME + 317 AWAY across 85 asset codes**, e.g. Detroit's current home
  kit is `09H0` on both discs. A PS2 recipe therefore names a uniform exactly
  the way an Xbox one does.

**One documentation drift, not a layout difference.** The Xbox module's
docstring places the `f32 1.0` at `Unif +0x2C`; on PS2 it sits at `Unif +0x34`
(chunk `+0x60`), with two small integers in between. Nothing this capability
writes is affected — the colour pair is at `Unif +0x24` on both, as the Xbox
`COLOUR_OFFSET` says.

### `ROST` — full parity, 76 of 76

All 76 chunks parse with **`tools/nfl_roster.py` unchanged** — the same parser
the shipped PS2 save editor uses on the save-side arena.

| measurement | result |
|---|---|
| `ROST` chunks found | **76** |
| decode with `nfl_roster` unchanged | **76 / 76**, 0 rejected |
| object version / root | **17 / `0x40`** on every one |
| LZ-compressed bodies | **0 / 76** |
| labelled `roster` | **1** (outer entry 5) |
| labelled `historic` | **75** |

**The boot roster is outer entry 5** — name id `0x4a37581d`, 593,760 bytes,
uncompressed, in `/VC_20919/0.`, the only object labelled `roster`. Its tables:

```
primary_players 2479   secondary_players 68   stadiums 82   teams 52
colleges 266   coaches 35   player_pointer_vector 241
team_labels 36   generated_names 485   historic_descriptors 75
```

2,479 + 68 = **2,547 player records**, exactly the population the Xbox
`nfl2k5.players.disc_roster` row names ("outer 5 main ROST, 2,547 records"),
and exactly the split the PS2 save editor reports for a save-side arena. The
other 75 are `historic` 53-man all-time squads (53 players, 1 team, 1 stadium,
1 coach each).

The identifying rule the tools use is the label, not the index: exactly one
`ROST` object must be labelled `roster`, and the catalogue refuses to build if
that is not true.

#### The editable fields hold on PS2

| field | location | check | result |
|---|---|---|---|
| jersey number | `record +0x20` bits 3..9 | every decoded value in 0..99 | **2,547 / 2,547** |
| face shield | `record +0x20` bits 15..16 | no record uses the reserved value 3 | 2,487 None · 42 Clear · 18 Dark |
| first / last name | `record +0x10` / `+0x14`, VC relative pointer | UTF-16LE, NUL-terminated inside the arena | 5,094 slots |

#### Fixed-allocation string budget

Capacity is the exact byte span the stored string occupies, terminator
included. Counting references across **all ten root tables** (players,
colleges, stadiums, coaches, team labels, generated names, historic
descriptors and teams), not just the player pools:

* **4,197 of 5,094 name slots are writable.**
* The other **897 are bare-terminator placeholders** (capacity 2) and are
  refused.
* **Every non-empty name string on PS2 is referenced exactly once.** This is
  stronger than the Xbox row, whose writer is scoped to "uniquely-referenced
  primary players" — on PS2 uniqueness never removes a slot beyond the empties.

Capacity histogram (bytes, both name fields, all 2,547 records):

```
 2:897   6: 13   8:169  10:665  12:977  14:873  16:658  18:337
20:113  22: 54  24: 16  26:  6  28:  3  30:  2  34:311
```

### What differed from Xbox

Three things, none of them blocking:

1. The `f32 1.0` field sits one slot later than the Xbox docstring says (above).
2. `/VC_20919` on PS2 also holds a `DATA/` subtree of IOP modules and network
   assets — 69 files under that path, only **5** of which are resource packs.
   Anything walking the directory must filter to the single-character pack
   names; both verifiers do, and say why.
3. The Xbox roster row's "uniquely-referenced" caveat is not binding on PS2:
   all non-empty names are singly referenced.

Everything else ported unchanged.

---

## 2. What the two lanes build

| file | role |
|---|---|
| `tools/nfl2k5_ps2_unif_color_target_catalog.py` | walks the disc, emits `reports/gameplay_tuning/nfl2k5_ps2_unif_color_catalog.v1.json` |
| `tools/nfl2k5_ps2_unif_color_patch.py` | recipe → new ISO via `replace_files` |
| `tools/nfl2k5_ps2_unif_color_verify.py` | independent verifier |
| `tools/validate_nfl2k5_ps2_unif_color.sh` / `.bat` | CI validators |
| `tools/nfl2k5_ps2_disc_roster_target_catalog.py` | walks the disc, emits `reports/gameplay_tuning/nfl2k5_ps2_disc_roster_catalog.v1.json` |
| `tools/nfl2k5_ps2_disc_roster_patch.py` | recipe → new ISO via `replace_files` |
| `tools/nfl2k5_ps2_disc_roster_verify.py` | independent verifier |
| `tools/validate_nfl2k5_ps2_disc_roster.sh` / `.bat` | CI validators |

Both writers follow the same shape:

```
stock ISO (read-only)  +  recipe  [+ pinned catalogue]
        │
        ├─ resolve every target against the operator's OWN image
        ├─ refuse anything that would move a pointer or change a size
        ├─ stage a byte-exact copy of each affected /VC_20919 pack, poke the spans
        └─ ps2_iso9660_writer.replace_files  →  NEW ISO, same byte length
                                             →  receipt with declared ranges
```

### What each refuses, and why

| refusal | colours | rosters |
|---|---|---|
| over-length replacement | a colour literal that is not exactly 4 bytes per word | a name needing more bytes than its slot holds |
| out of range | a selector outside the 634 | a player index outside the pool |
| unsafe target | a `Unif` whose descriptor does not resolve to the proved offset | a shared name string; a zero-capacity placeholder |
| recompression that does not fit | an LZ-compressed body | an LZ-compressed body |
| image mismatch | live probe digest ≠ pinned catalogue | live body digest ≠ pinned catalogue |
| no-op | the record already holds those colours | the record already holds those values |
| destination exists | refused before anything is created | refused before anything is created |

**On recompression.** The brief for these lanes allows a writer either to
recompress into the fixed span or to refuse. Since **0 of 634 `Unif` and 0 of
76 `ROST` bodies are compressed on the retail disc**, shipping an unexercised
refit path would be claiming more than the evidence supports. Both writers
refuse, and the refusal names the reason. Both test suites exercise that
refusal against a synthetic compressed chunk, so the branch is covered even
though stock media never reaches it.

### What each verifier proves

Neither imports the patcher, nor `ps2_iso9660` (the ISO writer's parser); the
roster verifier additionally does not import `nfl_roster`, the parser its
writer uses. The container layout, the VC pointer rule and the ten root tables
are restated so the two implementations can disagree. Each verifier:

1. re-derives the pack extents and the resource walk from the written image;
2. compares the two images across every replaced extent and permits a
   difference **only inside the declared ranges** — a stricter claim than the
   ISO verifier makes, because that one checks the writer's staged content
   rather than the source;
3. checks each declared range against the receipt's before/after digests;
4. re-decodes every resource of its family in the written image;
5. for rosters, requires that **every table count *and* byte offset is
   unchanged** — the arena did not move;
6. delegates to `ps2_iso9660_verify.verify_replacement` last, so this module's
   narrower findings name the offending byte first.

---

## 3. Real-disc trials

Both trials ran on a **copy**. The source image was opened read-only and is
byte-identical afterwards. The output images live in gitignored scratch and are
not committed. **No emulator was run: these prove the bytes, not the pixels.**

Full records: `reports/gameplay_tuning/nfl2k5_ps2_unif_color_trial.v1.json` and
`reports/gameplay_tuning/nfl2k5_ps2_disc_roster_trial.v1.json`.

Source image both times: volume id `50137`, 2,277,872 blocks of 2,048 bytes,
**4,665,081,856 bytes**, 0 slack, 78 entries.

### Colours — Detroit's current HOME facemask

| | |
|---|---|
| target | selector `09H0`, outer 1770 (`0x9a4832d6`), `/VC_20919/0.` |
| edit | facemask → `#12FF34`; turtleneck untouched |
| declared range | 1 × 8 bytes at image offset 1,069,963,344 |
| replaced file | `/VC_20919/0.`, LBA 14639, 1,073,741,824 bytes in and out, 0 zero-filled |
| stock extent sha256 | `aedd794680a0450b09db5c1502b937ae0abc5b8be6b1e80881cd004a555fe16d` |
| written extent sha256 | `34cc96a20f275f98f5f5df0a785a325cfd751aef2cbf0327ce48d7b120d7e3b2` |
| span before / after sha256 | `ec1cfe77…4dc76e63` → `07d3e343…f656ef36` |
| destination size | 4,665,081,856 — identical to the source |
| `nfl2k5_ps2_unif_color_verify` | **PASS** — 1 edit checked, **634** `Unif` records decoded, 1,073,741,816 unchanged bytes compared inside the replaced pack |
| `ps2_iso9660_verify` | **PASS** — 3,591,340,024 unchanged bytes compared outside it |
| wall clock | 6m55s write, 1m45s verify |

### Rosters — boot-roster primary player 0

| | |
|---|---|
| target | outer 5, label `roster`, arena at image offset 32,890,912, 593,760 bytes |
| edit | first name rewritten at equal length; jersey number → 7 |
| declared ranges | 4 bytes at 32,935,912 (packed word) and 12 bytes at 33,397,136 (name allocation) |
| replaced file | `/VC_20919/0.`, 1,073,741,824 bytes in and out, 0 zero-filled |
| destination size | 4,665,081,856 — identical to the source |
| `nfl2k5_ps2_disc_roster_verify` | **PASS** — 2 edits (1 name, 1 packed), **76** `ROST` resources decoded, all ten table counts and offsets unchanged, 1,073,741,808 unchanged bytes compared |
| `ps2_iso9660_verify` | **PASS** — 3,591,340,024 unchanged bytes compared |
| wall clock | 4m17s write, 1m25s verify |

A note on cost: `replace_files` replaces whole files, and the packs are 1 GiB
each, so a single eight-byte poke stages and rewrites a gibibyte. That is the
price of the fixed-allocation guarantee, and it is why the writers stream the
staging copy rather than holding it. The ISO writer itself does read each
staged pack into memory, so a colour recipe touching both packs that carry
`Unif` resources costs about 2 GiB of RAM; split such a recipe if that matters.
The roster lane never has this problem — the boot roster and all 75 historic
rosters live in `/VC_20919/0.`, so a roster recipe is always one file.

---

## 4. Retail-free discipline

* **Colours catalogue** carries selectors, offsets, lengths and the SHA-256 of
  each eight-byte span — **never the retail colour words**. They are read from
  the operator's own image at edit time, the same rule the Xbox writer follows
  ("raw offsets and retail bytes never enter the shareable project").
  `--inspect <selector>` prints them for the operator from their own disc.
* **Roster catalogue** carries player names and jersey numbers — public roster
  data, explicitly in scope — with offsets, capacities, reference counts and
  digests. The **packed equipment word** (which also carries the face-shield
  selector) and every rating byte are recorded **as digests only**; the writer
  reads the live word from the operator's image. When in doubt, hash.
* No trial image, no chunk and no disc byte is committed anywhere.

---

## 5. Tests

`tests/mod_editor/test_nfl2k5_ps2_unif_color.py` — **26 tests**
`tests/mod_editor/test_nfl2k5_ps2_disc_roster.py` — **33 tests**

Every image is built in a temp directory: a real ISO9660 volume, a real
two-pack `/VC_20919` archive, a real outer index, and real `Unif` / `ROST`
chunks. A CI runner with an empty disk runs both files green.

The load-bearing ones:

* the colour offset is **derived, not assumed** — moving a fixture's descriptor
  pointer moves the derived offset and clears the "matches Xbox" flag;
* one edit yields an image of the source's exact byte length with at most the
  declared bytes different anywhere in it;
* the untouched word of an edited colour pair survives;
* a masked roster write preserves every unrelated bit of its word;
* **every refusal leaves no destination behind** (asserted for each);
* **the verifiers can fail** — a stray byte outside the declared ranges, a
  declared span rewritten behind the receipt's back, a broken `Unif` object, a
  moved `ROST` table pointer, and a receipt that lies about the stock bytes
  each raise. A verifier that cannot fail is a rubber stamp;
* a source-text assertion that each verifier does not import the modules it is
  supposed to be independent of.

Both validators pass under system Python 3.9 and the 3.11 venv:

```
bash tools/validate_nfl2k5_ps2_unif_color.sh    # NFL2K5_PS2_UNIF_COLOR_VALIDATION_PASS
bash tools/validate_nfl2k5_ps2_disc_roster.sh   # NFL2K5_PS2_DISC_ROSTER_VALIDATION_PASS
```

---

## 6. What remains before either row can claim `offline-writer-proved`

Both surfaces have the artefacts a row needs; what is left is integration work
that this branch deliberately does not do, because rows land in serialized
commits.

For **both**:

1. **The registry row itself**, in a commit that also widens `SURFACE_GAMES`.
   `validate_registry.py` asserts `coverage == expected_coverage` by equality,
   so a row without its `SURFACE_GAMES` entry and the entry without its row
   both fail CI. `colors` and `players_rosters` are currently
   `_LEGACY_GAMES`; each must become `("nfl2k5_ps2", "nfl2k5_xbox")`.
2. **The pin cycle.** Every `*_PINS` dict and every capability-count literal
   moves. Two audits have named the covered-capabilities pin as the likeliest
   CI breaker; treat the row commit as the watched one.
3. **A CHANGELOG entry and the version-truth bump it forces.**
4. Nothing in `mod_editor/` is touched by this branch, so no GUI re-seal is
   owed — but a row with `gui.expose: true` would need one.

Row-specific:

* **`nfl2k5ps2.colors.unif_words`** — the honest classification today is
  `offline-writer-proved` with `runtime.status: "not-tested"`, mirroring the
  Xbox row, whose own summary says "fixed-size write/reopen is offline-proved;
  a controlled runtime capture is still outstanding". The PS2 row inherits that
  caveat exactly, and must not claim more: no PCSX2 capture has confirmed which
  material each word tints on this platform.
* **`nfl2k5ps2.players.disc_roster`** — same classification, same
  `runtime.status`. It must also carry the Xbox row's live caveat that **a
  loaded roster or franchise save may override the disc seed**, which on PS2 is
  the more likely path because the memory-card writer already ships.

Neither row may claim `runtime-proved` without its own PenguinScreen2 witness.
The colours row would need a controlled capture that isolates the facemask and
turtleneck materials; the roster row needs an edited player seen in-game from a
fresh franchise started off the patched disc, with no roster save loaded.

Deliberately out of scope here: a GUI, the `mod_editor/core` service wrapper
either row would need to appear in 2K5 Mod Studio, and any edit beyond the
fields the Xbox lane proved.
