# Madden NFL 09 (PS2) — Text & Team Identity

What the studio's third page edits on a Madden NFL 09 (USA, `SLUS-21770`)
PlayStation 2 disc: the **thirty-two NFL teams' names and colours**, written
into every copy of the row the disc's own databases agree on.

Lane: `mod_editor/games/madden09_ps2/identity_lane.py`.
Registry row: `madden09ps2.identity.team_records`, surface `colors`,
classification **`offline-writer-proved`**.
Validators: `tools/validate_madden09_ps2_identity.{sh,bat}`.
Evidence: [`measured/madden09_ps2/identity_blast_radius.json`](measured/madden09_ps2/identity_blast_radius.json).

**Nothing here has been booted.** Every claim below is about bytes on a disc
image. §6 says exactly what a boot would have to show.

**Evidence tags.** **[M]** measured — a read-only command was run against the
owner's own disc and the number is quoted. **[S]** sourced — someone else's
finding, cited. **[A]** assumed — inference, not verified.

**Retail-free.** Everything below is a field name, a width, a count, an index
or a digest. No name, colour value or byte from the game appears here, in the
lane, in its tests or in its evidence file.

---

## 1. What the page edits

One target is a **team**, not a record. The lane lists 32 of them — the NFL
teams — each labelled from the values read off the user's own image, and each
offering seven controls:

| control | kind | field(s) written | width on the disc | offered |
|---|---|---|---|---|
| Nickname | text | `TDNA` | 17 bytes | 16 characters |
| City | text | `TLNA` | 18 bytes | 17 characters |
| Abbreviation | text | `TSNA` | 7 bytes | 6 characters |
| Short name | text | `TMNC` | 17 bytes | 16 characters |
| Primary colour | `colour_argb` | `TBCR`, `TBCG`, `TBCB` | 8 bits each | `#RRGGBB` |
| Secondary colour | `colour_argb` | `TB2R`, `TB2G`, `TB2B` | 8 bits each | `#RRGGBB` |
| City id | int | `CYID` | 8 bits | 0–255 |

The four widths are the schema's [S] and are read off the file's own field
directory at run time, never from a table written down in the lane [M].

**Text.** Latin-1 — the only encoding this format carries — NUL-padded to the
field. A name is offered one byte short of its field's width so the terminator
survives; a longer one is refused with the length it has and the length it
must fit. A blank box means *keep what is there*.

**Colours.** The record has no alpha channel: a colour is three separate
one-byte fields. The editor takes `#RRGGBB` and also `#AARRGGBB`, because a
shell drawing a packed-ARGB control hands back eight digits — and **the alpha
byte is dropped**, which the field's own help text says rather than leaving the
user to discover it. A blank box means *keep what is there*.

**City id.** An index into a `CITY` table, not a name. The city *names* live in
`TEMPLATE.DAT` only, which this lane does not write (§2), so changing `CYID`
re-points a team at a different shipped city and cannot invent one. `-1` means
*keep what is there*.

### 1.1 Measured, and deliberately not edited

These fields are in the same record. They were read on the retail disc and are
**not** offered, because an editor is not the place for a hypothesis:

| field | what is known |
|---|---|
| `TCDO` | tracks `TGID` on 32 of 32 teams [M]. `Hypothesis:` a colour or logo index [S] |
| `TCRP` | tracks `TGID − 1` on 31 of 32 teams [M]. Same hypothesis |
| `TGPT` | tracks `TGID` on 32 of 32 teams [M]. Same hypothesis |
| `TCTX` | tracks `TGID` on 32 of 32 teams [M]. Same hypothesis |
| `TGID` | the key every other copy of the row is matched by; changing it re-points the row rather than renaming the team |
| `CGID`, `DGID`, `LGID` | conference, division and league ids — structural keys, not identity |
| `TORD` | the order the team is listed in |
| `DISN` | read, not decoded [A] |

Four of these correlating almost perfectly with `TGID` is *consistent* with a
colour or logo index and consistent with several other readings. Until one of
them is shown to change something on a screen, offering it would be asking the
user to run the experiment.

---

## 2. The blast radius, measured

A rename that reaches one copy of a team's identity and not the others leaves
the game reading whichever it opened first. So the first question was **how
many copies exist**. Measured on the owner's retail disc [M]:

| where | rows | carries the 32 NFL teams? | identity identical to the anchor | this lane writes it |
|---|---:|---|---:|---|
| `/DATA/DB_TEAMS.DAT` member *n*, `n` = 0..31, `TEAM` record 0 | 1 per member | yes, `TGID` 1..32 | — (the anchor) | **yes** |
| `/DATA/STRMDATA.DB`, `TEAM` | 234 | yes, plus 202 historical squads | **32 of 32** | **yes**, when it agrees |
| `/DATA/TEMPLATE.DAT` member 1, `TEAM` | 33 | yes, plus the free-agent pool | **32 of 32** | no — `FE.QKL` |
| `/DATA/TEMPLATE.DAT` members 2, 3, 4, `TEAM` | 185 / 194 / 194 | **no** — `TGID` 33..1011 | n/a | no |
| `/DATA/TEMPLATE.DAT` members 6, 12, 16, `TEAM` | 0 each | **no** — shipped empty | n/a | no |
| `/DATA/DB_TEAMS.DAT` members 32..234, `TEAM` | 1 per member (203 members, one empty) | **no** — the historical squads and the free-agent pool | n/a | no |
| `TEXT` string banks, six containers | 543 members of 14,748 | spell a team's name as prose | n/a | no — §2.3 |

`TEAM` is one schema wherever this page meets it: **65 fields, a 116-byte
bit-packed little-endian record**, in all 235 `DB_TEAMS.DAT` members and in
`STRMDATA.DB` [M][S]. `TEMPLATE.DAT` carries `TEAM` in seven members and in
four *other* schemas — 66 fields/116 bytes in member 1, 70/128 in 2, 68/128
in 3, 128/180 in 4, 6, 12 and 16 [M] — so a page that assumed one shape would
be wrong there even if it were allowed to write it.

### 2.1 The two copies the lane writes

One recipe writes both, so a rename cannot leave them disagreeing:

1. the `DB_TEAMS.DAT` member's `TEAM` record — the anchor the target names;
2. the `STRMDATA.DB` `TEAM` record whose `TGID` matches.

**`STRMDATA.DB`'s rows are not in `TGID` order** [M] — team 1 is record 106,
team 4 is record 0, team 19 is record 174 — so the second copy is resolved by
reading the field off every record, never by arithmetic on a position. The
synthetic fixture the tests and CI run on lists its two teams in the *opposite*
order to the container's members for exactly this reason: a lane that matched
by position would write the wrong team there and the verifier would say so.

Neither file is named by either preload cache [M]: `GAME.QKL` names 29 `/DATA`
files and `FE.QKL` 28, and `DB_TEAMS.DAT` and `STRMDATA.DB` are in neither
list. The lane re-reads that list off the user's own image at catalogue time
rather than trusting a table written down in the code; if an image ever does
name `DB_TEAMS.DAT`, the whole page refuses, and if it names `STRMDATA.DB` the
second copy is left out and the catalogue says which cache named it.

### 2.2 The copy the lane will not write

`TEMPLATE.DAT` member 1 carries a **byte-identical third copy** of all 32
teams' identity fields [M]. It is not written, because `TEMPLATE.DAT` is named
in `/DATA/FE.QKL`, the front-end preload cache, which carries a copy of at
least some of what it names [M] — the owner's research confirms one member of
`TEMPLATE.DAT` embedded verbatim inside `FE.QKL` [S]. Rewriting the container
and not the cache would leave a stale copy behind, so the sibling roster and
text pages refuse the same file and this one does too.

**What that means for a user:** a team renamed by this page is renamed in two
of the three databases that carry its identity, and not in the third. **Which
copy any given screen reads is not established** [A] — this project has not
traced a screen back to a database — so no claim either way is made here, and a
screen still showing the old name is the first thing a boot should be watched
for (§6).

### 2.3 A team's name is also prose

Team names appear as ordinary text in the disc's story and online string banks.
Of the 14,748 `TEXT` members, **543 carry at least one of the 32 teams' four
identity strings — 464 of them a string five characters or longer** — in six
containers (`STORYMSG.DAT` 451, `STRYHDLN.DAT` 50, `STRYTEXT.DAT` 33,
`OSDKSTRN.DAT` 6, `STRYEMAL.DAT` 2, `STRYCPTN.DAT` 1) [M].

This page does **not** touch them. A team renamed here still has the old name
in the story generator's headlines; the Menus & UI page's text lane is where a
string is edited, one slot at a time, and it edits exactly those six
containers. The number is measured so the gap is a figure rather than a shrug.

(Six containers larger than the reader's 96 MB cap — the speech, music and
movie files — were not scanned. They hold no `TEXT` bank this instrument could
reach, and the same cap bounds the text lane's own 14,748 [M].)

### 2.4 What a relocation would need, and why this is not it

The owner's research records that a full relocation spans two files and two
schemas: the team's **stadium** (`STAD`) and its **city name** (`CITY`) exist
only in `TEMPLATE.DAT` members, never in `DB_TEAMS.DAT` [S] — and
`TEMPLATE.DAT` is the container above that this module refuses. So this page
renames and recolours a team where it plays; it does not move it. That is a
scoping fact, not a plan.

---

## 3. Why a record edit is a bounded write

A TDB field owns a fixed run of bits inside a fixed-stride record, so writing
one **cannot change a length**: the database comes back the same size, the
container member it sits in comes back the same size, and the ISO extent it
came from is rewritten in place. A rewrite that would change any of those is
refused rather than allowed to move bytes the lane cannot account for.

The writer is the sibling roster page's, **imported and not copied**:
`ea_tdb.write_records` for the record, `ea_terf.rewrite_member` for the
container member, `tools/ps2_iso9660_writer.replace_files` for the image. The
two pages cannot drift apart on the one thing they both do.

The four CRC-32/MPEG-2 checksum sites EA stores in a TDB header are recomputed
on every write (`ea_tdb.recompute_crcs`) and re-derived from the destination's
own bytes by the verifier (`ea_tdb.verify_crcs`). The algorithm was proved
first, against 4,806 stored checksums across 252 databases on the retail disc
[M].

The source is opened read-only and never written; the destination must not
already exist and may not be the source.

### 3.1 When a second copy disagrees

Agreement is checked **field by field, on the values being written**: the
`STRMDATA.DB` copy is written only where it says today what the anchor said
before the edit. A row that already differs is not a copy of this team's
identity, and writing it would be a guess dressed as consistency — so it is
left alone and the receipt names the field that made it differ. The catalogue
says the same thing before a build: each target lists its copies and, for each,
the fields that copy will not take. On the retail disc all 32 teams' two copies
agree, so 32 edited teams write 64 rows [M]; the disagreement path exists for a
modified image and is covered by tests.

---

## 4. The verifier

`identity_lane.verify_build` **imports none of the writer.** It uses the
repository's independent ISO verifier for the container-level claim, this
module's *reader* for the databases, and `ea_tdb.verify_crcs` for the
checksums. The receipt is an input to be checked, never evidence. Five things
are proved:

1. outside the declared byte ranges the destination is the source, the two
   images are the same size, and no untouched file's extent moved;
2. every edited value **reads back** from the destination's own container,
   member, table, record and field — and from the bare database beside it,
   where a second copy was written;
3. inside each edited database, every byte that differs from the source lies
   in a declared field span or a checksum slot, so a write that wrote correctly
   *and scribbled somewhere else* is caught even though it is inside a declared
   ISO range;
4. all four kinds of checksum in each edited database agree with the bytes
   that are there;
5. every written name is the text followed by **NULs to its own field's
   width** — the format's padding rule, re-expressed in the verifier rather
   than borrowed from the encoder, so a writer that stopped padding and left
   the previous name's tail behind fails even though every value reads back.

Each of the five has a test that makes it fail
(`tests/mod_editor/test_madden09_ps2_identity.py`).

---

## 5. The real-disc trial

One team's **abbreviation** and **primary colour**, on `DB_TEAMS.DAT` member 0
of the owner's retail image. Source opened read-only; the destination was
written to scratch and deleted as soon as the verifier had passed.

| | |
|---|---|
| source | 1,657,339,904 bytes, `SLUS-21770` retail |
| destination | 1,657,339,904 bytes — the same size |
| rows written | 2: `DB_TEAMS.DAT` member 0 `TEAM` record 0, and `STRMDATA.DB` `TEAM` record **106** — matched by `TGID`, not by position |
| copies not written | none; both copies agreed |
| declared ranges | 4: each file's whole extent (2,585,792 + 5,160,728 bytes) and each directory record's 8-byte length field |
| bytes declared | 7,746,536 |
| verdict | **PASS** — 8 values read back, 2 databases re-parsed, **470 of 470 checksum slots correct**, 0 undeclared changed bytes |
| ISO comparison | 197 entries and 1,649,593,368 unchanged bytes compared |

Two adversarial flips on that same destination were both refused: one byte
**outside** every declared range ("no declared range covers it"), and one byte
**inside** a declared ISO range ("the destination's bytes hash to …"). The
untouched image then re-verified PASS.

The full numbers, the per-team copy map and the two databases' before/after
digests are in
[`measured/madden09_ps2/identity_blast_radius.json`](measured/madden09_ps2/identity_blast_radius.json).

---

## 6. What still needs a boot

**No emulator has booted a rebuilt Madden 09 disc.** This page's classification
is `offline-writer-proved` and will stay there until it has. The witness:

> The owner opens **Team Select**, finds the edited team, and reads the
> **renamed abbreviation** where the old one was — then looks at the
> **helmet and jersey preview** and sees the **new primary colour**.

Three further things a boot would settle, none of them claimed here:

* whether the `TEMPLATE.DAT` copy this page refuses (§2.2) shows the old name
  anywhere the user would see it;
* whether `CYID` alone moves anything on screen, or whether the city name a
  screen draws comes from the `CITY` table this page does not write;
* whether any of `TCDO`, `TCRP`, `TGPT` or `TCTX` (§1.1) is in fact the logo
  or colour-scheme index the hypothesis suggests — the experiment is to change
  one on a rebuilt disc and look, which is a runtime question and not an
  editor's.

The story banks (§2.3) are a **known** gap, not a question: the old name stays
in 543 `TEXT` members until the Menus & UI page edits them.

---

## 7. Where the code is

| file | what |
|---|---|
| `mod_editor/games/madden09_ps2/identity_lane.py` | the lane: catalogue, `check_edit`, recipe, plan, build, the independent verifier, the synthetic databases |
| `mod_editor/games/madden09_ps2/containers.py` | the disc reader, and the synthetic disc the lane's fixture is built on |
| `mod_editor/games/_formats/ea_tdb.py` | the TDB reader, writer and the four checksums |
| `mod_editor/games/_formats/ea_terf.py` | the container reader and same-size member rewrite |
| `tools/ps2_iso9660_writer.py` / `_verify.py` | the bounded image write, and the independent check of it |
| `tests/mod_editor/test_madden09_ps2_identity.py` | 67 tests, on synthetic databases only |
| `tools/validate_madden09_ps2_identity.{sh,bat}` | the shipped-tree validators |

Run it without a window:

```
python3 -m mod_editor.games.madden09_ps2.identity_lane --source DISC.iso
python3 -m mod_editor.games.madden09_ps2.identity_lane --source DISC.iso \
    --recipe edits.json --destination new.iso --report receipt.json
```
