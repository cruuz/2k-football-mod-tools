# Madden NFL 09 (PlayStation 2) — what the module does today

The second game on the Game Studio shell, and the first written *for* it: the
module ships no window of its own. `studio_window` points at the core shell,
which draws the same fourteen pages every studio has. A lane reaches its page
by being a lane; a page with no lane says why in one sentence.

This document is the honest inventory: what each page does today, what is
measured, what is merely sourced, what is assumed, and — at the end — the list
of things this module deliberately does **not** claim.

**Evidence tags, on every load-bearing claim.**
**[M]** measured — a read-only command was run against a disc this box holds
and the number is quoted. **[S]** sourced — someone else's finding, cited.
**[A]** assumed — inference, not verified; treat it as a question.

**Retail-free.** Everything below is a name, an offset, a length, a count or a
digest. No member payload, no decoded pixel and no string from the game
appears here or in the code.

---

## 1. The discs

Two images are recognised, and they are **not the same disc** [M]:

| | retail | Deluxe |
|---|---|---|
| serial | `SLUS-21770` | `SLUS-21770` |
| boot file | `SLUS_217.70` | `SLUS_217.70` |
| boot ELF SHA-256 | `adb400ba…f9f68c4c` | `d1cb5459…7588a515` |
| PCSX2 CRC | `38014255` | `084562FF` |
| image SHA-256 | `b34e8a6a…a82f6427` | `d331c5e4…4bc1be20` |
| image bytes | 1,657,339,904 | 1,846,476,800 |
| files | 187 | 185 |

The serial alone is not specific enough to act on, so the identifier keys on
the **boot ELF digest** and says which edition it found. Thirteen `/DATA`
files differ between the two [M] — the Deluxe team rewrote the uniform,
stadium, field-art and database containers — so a lane that reads
`UNIFORMS.DAT` genuinely gets different bytes depending on which disc is open.

A disc booting another serial is refused with one sentence naming what was
expected. A Madden 09 re-cut whose ELF matches neither digest is **not**
refused: it is reported as `unknown edition`, catalogued like any other, and
nothing about it is claimed. Every lane here is read-only, so nothing is
risked by listing it.

Identity comes from `Ps2DiscIdentifier` (ISO9660 volume + `SYSTEM.CNF` +
boot ELF) with the edition layered on top in `disc_identity.py`.

---

## 2. The containers, and the one rung everything stands on

Every large `/DATA/*.DAT` is an EA `TERF` container. That format is fully
decoded and documented in [`EA_TERF_FORMAT.md`](EA_TERF_FORMAT.md) — header,
chunk chain, member directory, codec table and the two implemented codecs —
and the reader is shared (`mod_editor/games/_formats/ea_terf.py`), so this
module contributes the *game-specific* half only: which files to walk, how
much of one it will hold in memory, and how to recover a container the disc's
own directory record understates.

Three facts from that document shape every lane below:

1. **Member offsets are relative to the `DATA` tag, not its payload** [M].
2. **An empty member still occupies one alignment unit** [M].
3. **A packed member's stored magic tells you nothing** [M] — 39 of 107
   containers change classification between their stored and decompressed
   bytes, so a member is classified only after it is unpacked.

And one that shapes what is *not* here: **there is no `LZH1` encoder**, in
this repository, in the owner's, or anywhere public [S]. An edited member can
be stored uncompressed — the retail disc itself ships 270 of `UNIFORMS.DAT`'s
725 members that way inside a `COMP` container [M] — but it cannot be
re-packed to its original size. Every writer in this module's future runs into
that, and none of them pretends otherwise.

### 2.1 Container size limit

The module reads a container up to **96 MB** and lists anything larger with
its size, unread. Madden 09's six speech and music containers run 124 MB to
415 MB [M]; counting their members is not worth half a gigabyte of memory, and
"listed but not read" is a state the catalogue names rather than a silent gap.

---

## 3. The pages

The shell's fourteen pages, in its order, and what Madden 09 has on each.

| page | lane | classification | what it does today |
|---|---|---|---|
| Uniforms & Equipment | `uniforms.mmap_export` | `extract-only` | see §3.1 |
| Names, Numbers & Faces | `players_rosters.team_databases` | `read-only-mapped` | §3.3 |
| Text & Team Identity | — | — | page note |
| Field Art & Create-Team Art | — | — | page note |
| Stadiums | — | — | page note |
| Presentation | — | — | page note |
| Menus & UI | `menus.text_members` | `read-only-mapped` | §3.4 |
| The Crib | — | — | page note |
| Audio | — | — | page note |
| Gameplay | `gameplay.executable_patches` | `unknown` | §3.5 — not drawn |
| Playbooks & Plays | — | — | page note |
| All Textures | `textures.container_inventory` | `read-only-mapped` | §3.2 |
| Saves | — | — | page note |
| Build & Share | — | core | the shell's own |

### 3.1 Uniforms & Equipment — the `MMAP` art lane

See §6 for the pixel-layout verdict, which is what decides whether this page
exports art or only describes it.

### 3.2 All Textures — the container inventory

`ReadOnlyLane`, `read-only-mapped`. Walks every `/DATA` file, opens the ones
that are containers, and lists them: chunk chain, alignment, member count,
codec histogram, and per-member offset, stored size, codec, unpacked size and
post-decompression format.

**Measured on the retail disc** [M]:

```
101 containers (of 107; six are over the 96 MB read limit)
36,195 members
codecs: 0 (stored) and 5 (LZH1) only
formats (first 256 members of each container, 9,063 classified):
  MMAP 4,901 · TEXT 1,288 · unclassified 764 · SMF 626 · TERF 500
  TDB 354 · DMF 300 · SCHl 167 · empty 137 · FNTS 14 · SKL1 8 · SEVT 3 · ELF 1
```

The format histogram samples the **first 256 members of each container**, and
every row records how many it sampled, so the numbers are never read as a
whole-container census. That is a speed decision — unpacking 36,195 `LZH1`
streams in pure Python is not free — not a format limit; the whole-disc census
is in `EA_TERF_FORMAT.md` §4.

Whole-disc walk: **about ten seconds** [M].

The lane caps its *target list* at 4,000 rows because a table is a table and
36,195 rows is a data dump; the document's counts stay complete either way.

### 3.3 Names, Numbers & Faces — the team databases

`ReadOnlyLane`, `read-only-mapped`. Madden 09's team, roster and tuning data
lives in **EA TDB v8 databases packed as `TERF` members** — plus one bare
database, `/DATA/STRMDATA.DB`, with no container around it [M]. The reader is
new and shared: `mod_editor/games/_formats/ea_tdb.py`.

**Measured on the retail disc** [M]:

```
355 databases   (235 in DB_TEAMS.DAT, 104 in GAMEDATA.DAT,
                 15 in TEMPLATE.DAT, 1 bare STRMDATA.DB)
2,151 tables
354,812 records
60,537 field definitions
```

Whole-disc walk: **about 24 seconds** [M].

The catalogue carries **field names, not field values**. A field name is the
schema and is identical on every disc; a record's contents are the user's game
data. A test asserts the point by searching the serialised catalogue for the
synthetic fixture's own string values and failing if it finds one.

Three things the TDB reader had to get right, each measured rather than
assumed:

- **Records are bit-packed LSB-first**, within the byte and within the field
  [M]. Some documentation of this format says MSB-first; under that reading
  the same bytes give a different team id for every player on one team and the
  same speed rating for all of them. LSB-first was cross-checked against three
  independent existing readers and validated field-by-field against five real
  databases: **2,321 records, 7,797 field definitions, zero mismatches** [M].
- **`version` is the only big-endian field in the header** [M]. Read
  little-endian it comes back 2048; read big-endian, 8. This is why two
  readers can disagree about the version of one file.
- **Strings are latin-1, never utf-8** [M]. EA stores 8-bit characters; a
  utf-8 decoder mangles them or refuses.

Reported but never checked: the four CRC sites (a file-header CRC, a per-table
prior-CRC and header-CRC, and an EOF CRC). This lane only reads, so verifying
them would be work with no consequence; recomputing them would be a writer,
which this is not.

Also measured and recorded rather than used as a bound [M]: `lenBits` is
`lenBytes * 8 - 1` in 561 of 561 tables (it is *not* the last field's end);
index blocks trail the record array rather than preceding it; and `dbSize` is
the last table's end plus four, not the file length.

### 3.4 Menus & UI — the text banks

`ReadOnlyLane`, `read-only-mapped`. Finds every `TEXT` member — a member whose
decompressed bytes are printable NUL-separated strings — and measures it:
string count, longest and mean length, printable ratio, and the SHA-256 of the
decompressed bytes.

**Measured on the retail disc** [M]:

```
14,748 TEXT members
14,748 strings          (one string per member)
3,242,117 bytes
```

That member count is exactly the whole-disc census in `EA_TERF_FORMAT.md` §4,
arrived at independently — this lane walks all 101 readable containers rather
than sampling, so the two numbers agreeing is a real cross-check. Whole-disc
walk: **about nine seconds** [M].

**The catalogue carries no string.** The contract's third rule is that a
catalogue holds names, offsets, lengths and digests and never payload, and a
catalogue is a file that can be shipped. So the strings are read from the
*user's own image* on demand, through `TextLane.preview` and the command
line's `--preview`, and are never stored anywhere.

**Why it is fast.** A member has to be unpacked before it can be classified,
but only its **first 32 bytes** — which is all `identify_member` looks at, and
where the codec stops. Only a member that matches is then unpacked in full.
Classifying by full decompression instead ran for over ten minutes on the
retail disc and was abandoned: 36,195 members, 4,269 of them `LZH1` streams
decoded in pure Python, for an answer the head already gave.

### 3.5 Gameplay — executable patches, nothing mapped

`CodePatchLane`, classification **`unknown`**, so the studio draws no editor
for it at all: the page states the classification and the registry's reason.

The pipeline is complete and proved on a synthetic ELF — plan against the
user's own boot ELF (address file-backed, original word as expected), emit a
`.pnach` naming that ELF's own PCSX2 CRC, verify by re-reading both
independently and failing a tampered file. **Every translation is refused by
name.**

The catalogue is six subject areas the owner's Madden 09 static-analysis work
has opened [S] — AI play calling, blocking dominance, blocking intent, catch
and fumble, defensive fatigue, double teams — each carrying the plain
statement that no word has been located for it. A target here is a question,
not a capability.

**No retail address or code byte is in this repository.** What the lane knows
about an executable it reads from the user's own image at run time.

A future PR that locates one site fills in a single `TRANSLATIONS` entry and
changes nothing else. That is what the synthetic proof exists to guarantee.

---

## 4. Pages with no lane, and why

Each has one sentence in `game.json`'s `page_notes`, shown under the shell's
own. In full:

- **Text & Team Identity** — team names and colours live in the `DB_TEAMS.DAT`
  databases, which the Names, Numbers & Faces page already lists; a separate
  identity editor waits on a database writer, and there is none.
- **Field Art & Create-Team Art** — `FIELDART.DAT` holds 642 `SMF` geometry
  members and 73 `MMAP` textures [M]; the textures are reachable through the
  same decoder as the uniforms, and no geometry format is decoded anywhere
  here.
- **Stadiums** — `STADIUMS.DAT` holds 651 `SMF` geometry members and 434
  `MMAP` textures [M]. Same position as field art: the textures are readable,
  the geometry is not decoded, and there is no editor for either yet.
- **Presentation** — the scorebug and broadcast overlays are drawn by the
  executable, and no data file on this disc has been mapped to them.
- **The Crib** — not a Madden concept; it is an ESPN NFL 2K5 feature and this
  page stays empty here on purpose.
- **Audio** — `SOUNDDAT.DAT`, `BGM.DAT` and the speech containers carry EA
  `SCHl` streams and `BNKl` banks; no decoder for either is built here and no
  public writer exists.
- **Playbooks & Plays** — playbook data has not been located on this disc by
  this project, and the owner's own research records that no playbook is among
  the members the `GAME.QKL` preload copies [S].
- **Saves** — a Madden 09 memory-card save is a different repository's
  tooling; this studio works off the disc.

---

## 5. What is measured, in one table

Every number this module quotes about a real disc, and the command that
produced it. All read-only; nothing was written to either image.

| number | value | source |
|---|---|---|
| retail image bytes | 1,657,339,904 | `identify` [M] |
| Deluxe image bytes | 1,846,476,800 | `identify` [M] |
| containers read | 101 of 107 | inventory lane [M] |
| members | 36,195 | inventory lane [M] |
| members classified | 9,063 (256/container sample) | inventory lane [M] |
| `MMAP` members in the sample | 4,901 | inventory lane [M] |
| `TEXT` members in the sample | 1,288 | inventory lane [M] |
| TDB databases | 355 | team-data lane [M] |
| TDB tables | 2,151 | team-data lane [M] |
| TDB records | 354,812 | team-data lane [M] |
| TDB field definitions | 60,537 | team-data lane [M] |
| retail boot ELF PCSX2 CRC | `38014255` | code-patch lane [M] |
| Deluxe boot ELF PCSX2 CRC | `084562FF` | code-patch lane [M] |
| inventory walk | ~10 s | wall clock [M] |
| team-data walk | ~19 s | wall clock [M] |
| `TEXT` members (full walk) | 14,748 | text lane [M] |
| strings in them | 14,748 (one per member) | text lane [M] |
| their decompressed bytes | 3,242,117 | text lane [M] |
| text walk | ~9 s | wall clock [M] |

And the same three lanes on the **Deluxe** disc [M], which is the point of
telling the two apart:

| number | retail | Deluxe |
|---|---|---|
| containers read | 101 | 100 |
| members | 36,195 | 34,600 |
| `MMAP` in the sample | 4,901 | 4,647 |
| `SMF` in the sample | 626 | 398 |
| TDB databases | 355 | 355 |
| TDB records | 354,812 | **340,806** |
| TDB field definitions | 60,537 | **60,569** |
| `TEXT` members | 14,748 | 14,748 |

The Deluxe team rewrote the databases and the geometry containers and left the
text banks alone, and the lanes say so without being told.

Reproduce any of them:

```
python3 -m mod_editor.games.madden09_ps2.inventory_lane --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.team_data     --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.text_lane     --source "<your>.iso"
python3 -m mod_editor.games.madden09_ps2.code_patches  --source "<your>.iso"
```

Every one of them also runs with no disc at all — `--selftest`, or the five
validators — because each lane builds its own synthetic source.

---

## 6. The `MMAP` verdict

*(See §3.1. This section records what was proved about the pixel layout, the
evidence for it, and what remains unknown.)*

---

## 7. What this module does not claim

Said plainly, because a page that stays quiet about its limits is worse than
one with fewer pages.

1. **No writer.** Nothing here writes to a disc image. Not one byte.
2. **No container rebuild has ever been booted.** `ea_terf.build_terf` and
   `rewrite_member` exist and are tested against synthetic containers, but the
   honest test — rebuild a container, put it back in an ISO, boot it in
   PCSX2, see the game load it — **has not been run** and cannot be run from
   this box. Until it is, no on-disc writer in this module can rise above
   `offline-writer-proved`, and none is offered at all.
3. **No `LZH1` encoder exists** [S], here or anywhere public. A replaced
   member must be stored uncompressed and pays about 3:1 in space; the
   fixed-allocation discipline the ISO9660 writer needs makes that a real
   budget question, not a detail.
4. **The container checksum question is open** [M/A]. No field in any
   container header varies with content in any way the reader could find, and
   the layout rules hold with zero residue across 47,769 members — but that is
   the whole of the search, and it is not proof. The circumstantial evidence
   is good (the community's Deluxe disc rewrites five containers, carries two
   defects the retail disc does not, and still plays [S]); it does not close
   the question.
5. **No PCSX2 replacement identity.** Naming a texture for a replacement pack
   needs the GS TEX0 and CLUT hashes PCSX2 computes at draw time, which come
   from a **GS dump of Madden 09 running on the rig**. No such dump exists.
   `replacement_identity` therefore returns `None` and the *Write PCSX2 pack*
   step refuses with that sentence rather than inventing a filename that would
   silently never match.
6. **No gameplay patch is mapped.** Six subject areas, zero located sites.
7. **`SMF` and `DMF` geometry, `SCHl` audio and `BNKl` banks are identified
   and not decoded.** Knowing a member's magic is not the same as reading it,
   and the module does not blur the two.

---

## 8. Where the code is

```
mod_editor/games/madden09_ps2/
  __init__.py         GAME, IDENTITY, the studio window spec (the core shell)
  containers.py       which /DATA files to walk; the synthetic disc
  disc_identity.py    retail vs Deluxe, by boot-ELF digest
  inventory_lane.py   the container inventory (ReadOnlyLane)
  uniform_art.py      the MMAP art lane
  mmap_art.py         the MMAP pixel decoder
  team_data.py        the EA TDB databases (ReadOnlyLane)
  text_lane.py        the TEXT banks (ReadOnlyLane)
  code_patches.py     executable patches (CodePatchLane, nothing mapped)
  game.json  registry.fragment.json  allowlist.fragment.txt  pins.json

mod_editor/games/_formats/
  ea_terf.py          the container (RC86; shared)
  ea_tdb.py           the database reader (RC87; shared)

tools/validate_madden09_ps2_{inventory,uniform_art,team_data,text,code_patches}.{sh,bat}
tests/mod_editor/test_madden09_ps2_*.py  tests/mod_editor/test_ea_tdb.py
```

The shared format packages are the point: a Madden 08, Madden 12 or NCAA
Football 09 module gets both readers for free — one reader already opens seven
EA PS2 discs unchanged [M].
