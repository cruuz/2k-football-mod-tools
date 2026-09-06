# NCAA Football 09 (PlayStation 2) — the database census, and what it means for the lanes

Every EA TDB database on the `SLUS-21752` disc, measured read-only: the tables,
their record strides and row counts, and every field's name, type, bit width and
bit offset — compared table by table against Madden NFL 09 (`SLUS-21770`), the
module this one is modelled on, and against NCAA Football 2004 (`SLUS-20719`)
five years earlier.

The machine-readable census is
[`measured/ncaa09_ps2/tdb-schema.json`](measured/ncaa09_ps2/tdb-schema.json).
This document is what it means.

**Evidence tags.** **[M]** measured on a disc this box holds; **[S]** sourced;
**[A]** assumed, and to be treated as a question.

**Retail-free.** Table names, field names, types, widths, offsets, record strides
and row counts. A field name is the schema and is identical on every copy of the
disc. **No record's contents are here, and none was read** — not a school name,
not a rating, not a string out of a text bank.

---

## The headline

The shared readers open this disc with **nothing changed** [M]:

| reader | result |
|---|---|
| `ea_terf.parse_terf` | 85 of 85 containers |
| `ea_terf.decompress_member` | 30,391 of 30,391 members |
| `ea_tdb.parse_tdb` | **580 of 582** databases |
| `ea_tdb.crc_sites` | **8,564 of 8,564** checksum slots hold the value they recompute to |
| `ea_schl.parse_stream_header` | 8,021 of 8,021 headers; 412 carry a codec that decodes |
| `ea_schl.parse_bank` | 728 of 728 banks, 1,213 sounds |

So **every reader ports**. What does not port is the *schema*: NCAA Football 09
is a different database wearing the same container.

| | NCAA 09 | Madden 09 |
|---|---:|---:|
| databases | 582 | 355 |
| tables | 3,702 | 4,108 |
| field definitions | 71,772 | 85,400 |
| distinct database shapes | 11 | 20 |
| distinct table names | 173 | 513 |
| **table names in common** | **77** | |

Whole-disc walk: **7.2 s** for the census, **7.5 s** for the module's own
catalogue lane [M].

---

## 1. Where the databases are

Four places, and the shape of the first is the surprise [M].

| where | databases | what they are |
|---|---:|---|
| `/DATA/LEAGUE.DAT` | 433 | **1 league database + 432 per-team roster databases**, `RLE1`-packed inside a `COMP` container |
| `/DATA/GAMEDATA.DAT` | 137 | 1 shared play library + 136 playbooks, stored, at members 4–140 |
| `/DATA/TEMPLATE.DAT` | 11 | fresh-dynasty templates, stored |
| `/DATA/STRMDATA.DB` | 1 | a bare database with no container around it |

**Madden 09 keeps one roster table; NCAA 09 keeps 432 databases.** Each per-team
database holds exactly two tables — `PLAY` and `DCHT` — and nothing else. Across
the 432: **24,717 player rows** in 30,240 slots, and **24,856 depth-chart rows**;
per team, 43 to 69 players [M]. Any roster writer for this disc rewrites 432
members of one container, not one table of one member, and each member is
`RLE1`-packed — for which an encoder already exists in `ea_terf`.

### The eleven schema shapes [M]

| digest | databases | tables | field defs | where |
|---|---:|---:|---:|---|
| `df5a5a49e22f07d7` | 432 | 2 | 89 | `LEAGUE.DAT` members 1–432 — the per-team rosters |
| `67b4694015115d66` | 137 | 19 | 214 | `GAMEDATA.DAT` — every playbook, one shape |
| `e473e37ca34051b6` | 1 | 25 | 695 | `LEAGUE.DAT` member 0 — the league |
| `8dacdabead510e43` | 1 | 92 | 1,401 | `TEMPLATE.DAT` member 1 — the dynasty save [A] |
| `dd3821b6b44f154b` | 1 | 49 | 781 | `TEMPLATE.DAT` member 0 — a 49-table league-and-game template [A] |
| `b1f609d5a46bd37c` | 3 | 3 | 103 | `TEMPLATE.DAT` — `PLAY` 8,142 / `DCHT` 7,655 / `TDYN` |
| `4195920798de6cb8` | 1 | 14 | 100 | `TEMPLATE.DAT` member 2 — the schedules [A] |
| `8b6c9de0cfec5eda` | 1 | 21 | 187 | `TEMPLATE.DAT` member 9 — user-created content [A] |
| `dcf3b77be887355f` | 1 | 12 | 230 | `TEMPLATE.DAT` member 10 — recruiting state [A] |
| `588b99d6da81633c` | 1 | 11 | 283 | `TEMPLATE.DAT` member 8 — options and showcase [A] |
| `384ccd466145a555` | 1 | 2 | 20 | `TEMPLATE.DAT` member 7 — two long-string tables |

The digests, counts and locations are measured; **what each `TEMPLATE.DAT` member
is *for* is read off its table names and is marked [A]** — `SACC`/`SBTN`/`SCHD`
for the schedules, `RCFN`/`RCPR`/`RCWK` for recruiting, `GOPT`/`OOPT`/`SOPT` for
options, the `U*` prefixes for user content. Member 1 is the widest at 92 tables
and carries `SEAI`, `HEIS`, `TRAN`, `PPRO` and the per-season stats tables, which
is the shape of a dynasty save [A].

Two databases the reader refuses are **§7**; they are recorded, not dropped.

---

## 2. `PLAY` — and the fact that decides everything

`LEAGUE.DAT` members 1–432, and three more in `TEMPLATE.DAT`: **86 fields, 52
bytes per record**, the same shape in 437 of the disc's 439 `PLAY` tables [M].

| | NCAA 09 | Madden 09 |
|---|---:|---:|
| fields | 86 | 110 |
| bytes per record | 52 | 104 |
| shared field names | **37** | |
| only here | 49 | |
| only in the control | 73 | |
| shared names whose width differs | 27 | |

### What is shared [M]

The twenty ratings and the body: `POVR PSPD PACC PAGI PSTR PAWR PCTH PCAR PTHP
PTHA PJMP PTAK PBTK PPBK PRBK PKPR PKAC PSTA PINJ PIMP`, plus `PPOS PJEN PWGT
PHGT PGID`, and the appearance block `PHED PSKI PHCL PNEK PEYE PFMK PHAN PVIS
PBRE PLSH PRSH PTEN`.

### What is missing, and why it is the whole story [M]

**There is no `PFNA` and no `PLNA`.** Madden 09's `PLAY` carries a first name and
a last name; NCAA Football 09's carries neither, because this game's players have
no names — a licensing fact you can read straight off the field directory. There
is no `PAGE` either: a college player has a **class**, not an age, and the disc
stores `PYER` (3 bits) and `PRSD` (2 bits) instead.

Also absent, and each one a Madden lane's subject: `PCON`, `PYRP`, `PMOR`,
`POID`, `TGID` (a player's team is *which of the 432 databases he is in*), and
the whole `PSA0..6` / `PSB0..6` / `PCSA` contract block Madden's franchise saves
carry.

### What is only here [M]

49 fields, and they are the college game: `PYER` (class), `PRSD` (redshirt),
`PRST`, `PTYP`, `PFMP` (face), `PPOE`, `PFGM`, `PFJS`, `HELM`, `PLEB`/`PREB`
(elbow pads), `PLWS`/`PRWS` (wristbands), `PSLO`, `PSLT`, `PTTO`, `PLFP`,
`PLMG`, `PHPD`, `PLHN`/`PRHN`, `PLSY`, `RCHD` (14 bits), the four shoe fields
`PFSH`/`PMSH`/`PRSH`/`PSSH`, and **`PF01..PF10` with `PL01..PL13`** — twenty-three
6-bit fields whose meaning is not established here.

These field names are the ones the owner's own NCAA draft-class research already
decoded from the NCAA 06 memory-card format — `PFMP` face, `PYER` college year,
`PRSD` redshirt, `PPOS`, `POVR`, `PJEN`, `PWGT`, `PHGT` and the rating block
[S: `NCAA-Draft-Class-Editor/CLAUDE.md`]. The on-disc `PLAY` record and that
138,240-byte draft-class file are the same record family, two years apart, and
that research is the best available reading of what each field means. NCAA 06 is
not on this box, so the two could not be diffed here; that is stated rather than
assumed away.

### The rating width, and what reading the records settled [M]

`POVR` and the twenty attribute fields are **5 bits wide** on this disc. Madden
09's are 7. A five-bit field holds **0..31**, so whatever a rating screen shows,
the stored value is not a 0..99 number in those bits.

That was recorded here as an open question, with the note that reading one
record would settle it. **It has been read.** 3,295 `PLAY` records across 62 of
the 432 rosters, sampled every seventh member [M]:

| field | range across the sample |
|---|---|
| `POVR` and all twenty attributes | **0..31**, every value in use |
| `PPOS` | 0..20 — 21 positions, and `PLPS` has exactly 21 rows |
| `PYER` | 0..3 — four class years |
| `PRSD` | 0..2 |
| `PJEN` | 0..99 |
| `PHGT` | 63..81 — inches, the same encoding Madden 09's `PHGT` uses |
| `PWGT` | 0..209 — pounds **less 160**, the same encoding Madden 09's uses |
| `PGID` | 70..30,012 |
| `PTYP` | 0..0 — zero in every record sampled |

`POVR`'s histogram is the shape that decides it: every value 0..31 appears, and
**536 of the 3,295 players (16%) sit on 31** — the top of the field, and far
above the next bucket. That is a scale that **saturates at its ceiling**, which
is what a 0..31 quantisation of a wider rating looks like from below.

**So the editor's bound is 31, the field's own**, and the roster lane offers
exactly that. What the game *draws* from those five bits is still not
established — no frame of NCAA Football 09 has been paired with a record here —
and no control claims a 0–99 number. The two facts are different and the module
keeps them apart: the bound is measured, the meaning is not.

---

## 3. `TEAM` — the 432 schools, and the colours that are not there

`LEAGUE.DAT` member 0: **74 fields, 124 bytes, 432 rows** in 444 slots [M].
(`TEMPLATE.DAT` carries two other `TEAM` shapes, 59 and 113 fields.)

| | NCAA 09 | Madden 09 |
|---|---:|---:|
| fields | 74 | 65 |
| shared names | 29 | |
| only here | 45 | |
| only in the control | 36 | |

**The names** [M]: `TDNA` (a 176-bit string, 22 bytes), `TMNA` (144 bits, 18) and
`TSNA` (56 bits, 7). Madden's `TDNA` is 136 bits and its `TSNA` the same width;
its `TLNA` (city) and `TMNC` (short name) **do not exist here**.

**The colours do not exist either.** Madden 09's `TEAM` carries `TBCR TBCG TBCB`
and `TB2R TB2G TB2B`; not one of the six is on this disc [M]. What *is* here:

- **`PACL`**, 64 rows of 5 fields — `CRED`, `CGRN`, `CBLU`, `PCID`, `PCNI` — a
  **palette**: a red, a green, a blue and a name index per colour id [M].
- **`CTCD`** (45 fields) and **`CTUN`** (28), the create-a-school colour and
  uniform tables, carrying packed 32-bit `CUBC`/`CUHC`/`CUJC`/`CUNC`/`CUPC`/`CUSC`
  words — and **0 rows on the disc**, because a created school is user data [M].

Which `TEAM` field selects a school's palette entry is **not established**.
`TPID` is 7 bits wide and `PACL` has 64 rows, which fits and is not proof [A].

Also only here, and the shape of a college league: `TCHL`/`TCHT`/`TCHW`/`TCHS`
(a conference-championship block), `TMAA`/`TMIA` (17 and 7 bits), `TCFP`/`TMFP`,
`DCAP`/`OCAP`, `TENV`, `SDUR`, `SGPC`/`SGSC`, `NCDP`, `MSID`, `TL35`.

**Conferences and divisions** are their own tables [M]: `CONF` 25 rows
(`CNAM` 160-bit string, `CGID`, `LGID`, `NCcl`, `CMNP`/`CMXP`, `CNPR`, `CPRS`)
and `DIVI` 10 rows (`DNAM` 160-bit, `CGID`, `DGID`). `DIVI` is identical on both
discs bar two widths. `CONF` is not: Madden 09's has the same four core fields
(`CGID`, `CNAM`, `LGID`, `NCcl`) and none of this one's other four — `CMNP` and
`CMXP` (a minimum and maximum member count), `CNPR` and `CPRS` — which is what a
conference that gains and loses schools needs and a fixed thirty-two-team league
does not.

---

## 4. `STAD` — a stadium table in the *league* database

`LEAGUE.DAT` member 0: **56 fields, 156 bytes, 242 rows** [M]. Madden 09 has no
`STAD` outside its `TEMPLATE.DAT`, so on the two discs' *league* databases this
table exists only here.

Strings: `SNAM` (240 bits, 30 bytes), `TDNA` (176), `SCIT` (168), `STNN` (144),
`SSTA` (120). Numbers: `SCAP` a 17-bit capacity, `SGID`/`STID`/`SORD`, and a
weather and surface block `SWFP`/`SWRP`/`SWSP`/`SWWP`, `SFTI`, `SFWE`, `STYP`,
`SRES`, `STDR`. Sixteen 16-bit `ST**` fields (`STfc`, `STlc`, `Stlc`, `STrf`,
`STri`, `STcl`, `STll`, `STrl`, `STRr`, `stcr`, `STlr`, `STrr` …) sit together
and are shaped like packed colour or material ids; their meaning is not
established here [A].

26 of the 56 names are shared with Madden 09's `TEMPLATE.DAT` `STAD`, 8 of those
at a different width [M].

---

## 4a. Kits — the table that is not there

The Uniforms page needs to know where a school's kit lives, and on this disc the
answer is **nowhere in a database** [M].

Every uniform-shaped table on the disc has **0 rows**:

| table | fields | bytes/rec | rows | where |
|---|---:|---:|---:|---|
| `CTTB` | 104 | 252 | **0** | `LEAGUE.DAT` member 0 |
| `CTCD` | 45 | 108 | **0** | `LEAGUE.DAT` member 0, `TEMPLATE.DAT` |
| `CTUN` | 28 | 76 | **0** | `LEAGUE.DAT` member 0, `TEMPLATE.DAT` ×2 |
| `USTG` / `USLG` / `USLE` | 19 / 11 / 11 | 40 / 24 / 24 | **0** | `TEMPLATE.DAT` |

They are the **create-a-school** tables: the packed 32-bit colour and pattern
words (`CUBC`, `CUHC`, `CUJC`, `CUNC`, `CUPC`, `CUSC`, `CUFM`, `CUJT`, `CUNO`,
`CUSR`, `CUSI`) a user's own uniform would be stored in, shipped empty because
nobody has made one yet. The only populated one anywhere near this shape is
`UPST` (64 fields, **6 rows**) in `TEMPLATE.DAT` member 9's user-content
database.

Madden 09, by contrast, ships **`UNIF` with 270 rows** [M] — a real uniform
table with a real row per kit.

**So a school's kit on this disc is 1,200 `MMAP` textures in `UNIFORM.DAT` and
not a record anywhere.** An editor for it is an art lane, and the schema has
nothing to offer it. That is a measured "no equivalent", not a gap.

---

## 5. `COCH` — coaches

`LEAGUE.DAT` member 0: **42 fields, 64 bytes, 315 rows** [M]. `CLFN` (80 bits,
10 bytes) and `CLLN` (104 bits, 13) are the names — so **the coaches have names
on this disc even though the players do not**. `TGID` ties a coach to a school;
`CCID`, `CDID`, `CPID` are ids; the rest is a tendency block (`CDTA`, `COTA`,
`CDPC`/`CRPC`/`CTPC`, `CDTR`/`COTR`, `CDST`/`COST`, `CHAR`, `COFS`, `COHT`).

Against Madden 09's 68-field `COCH`: **20 shared names, 22 only here, 48 only in
the control**, 16 widths differ [M]. `TEMPLATE.DAT` member 1 carries a wider
84-field `COCH` for the dynasty save.

---

## 6. Playbooks — the one place NCAA and Madden agree completely

`GAMEDATA.DAT` holds 137 databases at members 4–140, **all one schema shape**
[M]: 1 shared play library (member 4) and 136 playbooks.

**Their nineteen tables are name-for-name identical to Madden 09's nineteen**
[M] — `ARTL PLCM FORM PBAU PBFM PBPL PBST PLRD PLYS PSAL SETL SETG SPKF PLYL
PBAI PLPD SGF\x00 SPKG SETP`, zero only here, zero only in the control. The
four-character-name quirk travels too: `SGF\x00` is a table name on both discs,
which is why the shared reader's `decode_name` was needed.

The widths do not agree, and one structural difference matters:

| table | NCAA 09 | Madden 09 | note |
|---|---|---|---|
| `PBPL` | 5 fields, 8 B | 6 fields, 28 B | **Madden has `name`; NCAA does not** |
| `PLYL` | 11 fields, 36 B, `name` 192 bits | 10 fields, 40 B, `name` 248 bits | the play names live here |
| `PBFM` | 5 fields, 40 B, `name` 264 bits | 9 fields, 28 B, `name` 144 bits | no `FAU1..4` here |
| `PBST` | 5 fields, 24 B, `name` 128 bits | 5 fields, 24 B, `name` 152 bits | 4 widths differ |
| `ARTL` | 86 fields, 56 B | 110 fields, 60 B | no `ls**`/`lt**` columns here |

So Madden 09's playbook rename writer looks for a play name in `PBPL` and would
find no such field. The names are all present, in seven tables — **13,817
name-bearing rows** across the 137 databases [M]: `PLYL` 4,322, `PBST` 3,266,
`PBFM` 2,356, `SGF\x00` 2,086, `SPKF` 1,510, `SETL` 236, `FORM` 41.

Capacity is the same story as Madden's: 2,301 of the 2,603 tables across the 137
databases are packed exactly full [M], so a rename is possible and an insertion
is not.

---

## 7. The two databases the reader refuses, and the field type behind them

`ea_tdb.parse_tdb` opens 580 of 582. The two it does not are recorded with its
own sentence rather than dropped from the catalogue [M]:

```
/DATA/STRMDATA.DB      field ASNA of table ANIN covers bits 0..400 of a record
                       that is 8 byte(s) long; the field directory is being read
                       at the wrong offset or the file is damaged.
/DATA/TEMPLATE.DAT:3   field SPFN of table RCFN covers bits 0..80 of a record
                       that is 8 byte(s) long; …
```

Reading those two field directories by hand shows why [M]. The shared reader
names five field types — 0 STRING, 1 BINARY, 2 SINT, 3 UINT, 4 FLOAT — and these
two databases declare **type 13** and **type 14**, which it does not name:

| database | type 13 fields | type 14 fields | tables affected |
|---|---:|---:|---|
| `/DATA/STRMDATA.DB` | 18 | 1 | `ANIN ANMM ANPG ANPO ANPR ANRE CAPT CSDC CSDP LGML HEAD STXT TICK PLCC RCFN RCLN` |
| `/DATA/TEMPLATE.DAT:3` | 2 | 0 | `RCFN RCLN` |

Every one of them has the same signature [M]: a **bit offset that is a multiple
of 32**, a **width that is a multiple of 8 and larger than the whole record**
(80, 104, 200, 400, 720, 800, 960, 2000, 2040 bits, and 2048 for the single type
14), in a record 8 to 20 bytes long whose *other* fields are ordinary UINTs. A
32-bit slot in the record and a declared maximum length is the shape of an
**out-of-record string** — the record holds a handle and the width is the pool
entry's ceiling. That reading is consistent with every instance and **is not
proved here** [A]; nothing in this module depends on it.

The 580 databases that do parse use only types 0–4 [M]: 60,586 UINT, 9,546 SINT,
1,077 STRING, 561 FLOAT, 2 BINARY.

Which tables these are matters. `RCFN` (8,191 rows) and `RCLN` (6,915 rows) are
the two largest tables in `TEMPLATE.DAT` member 3 and are, by name and by size,
a **first-name and last-name pool** — the names a dynasty's recruits are drawn
from. **The one place on this disc where player names live is behind the type-13
refusal.** `CAPT` (3,045 rows), `HEAD` (3,107) and `STXT` in `STRMDATA.DB` are
the same shape.

Naming those two types is the single highest-value change to the shared reader
for this game, and it is being made elsewhere; this module records the refusal
and does not work around it.

---

## 8. The generation comparison — NCAA Football 2004

Five years earlier, `SLUS-20719` [M]:

| | NCAA 2004 | NCAA 09 |
|---|---:|---:|
| `/DATA` containers | 36 | 85 |
| databases parsed / refused | 521 / 4 | 580 / 2 |
| tables | 3,091 | 3,702 |
| field definitions | 57,179 | 71,772 |
| per-team roster databases | 390 | 432 |
| playbook databases | 124 | 137 |
| distinct table names | 135 | 173 |
| **table names in common with NCAA 09** | **101** | |

Same `TERF` chains, same three codecs, same `LEAGUE.DAT`-of-per-team-databases
architecture. **And the same four refusals**: `RCFN.SPFN`, `RCLN.SPLN`,
`CSDC.SEDP`, `ANIN.ASNA` — the type-13 field is not a 2008 invention.

Table by table, NCAA 2004 is far closer to NCAA 09 than Madden 09 is [M]:

| table | 2004 vs 09 shared names | Madden 09 vs 09 shared names |
|---|---|---|
| `PLAY` | 59 of 65 / 86 | 37 of 110 / 86 |
| `TEAM` | 57 of 62 / 74 | 29 of 65 / 74 |
| `COCH` | 36 of 42 / 42 | 20 of 68 / 42 |
| `STAD` | 52 of 54 / 56 | 26 of 74 / 56 |
| `CONF` | 8 of 8 / 8 | 4 of 4 / 8 |

**The NCAA line is its own schema family.** A field map written for this disc is
most of a field map for every NCAA Football on PS2; a field map borrowed from
Madden is not.

---

## 9. "Send to Madden" — what is and is not on this disc

The draft class NCAA Football writes for Madden is a **memory-card save the game
produces at runtime**, not a file on the disc, and no table on this disc holds
one [M]. What the disc does carry, and what a draft-class tool would need:

- the **record shape** — `PLAY`, 86 fields, the same family as the 86-byte
  NCAA-06 draft-class record the owner reverse-engineered [S];
- the **position tables** the export draws its labels from: `DRPS` 17 rows
  (`PDST`, a 24-bit string), `PLPS` 21 rows (`PPST`, 32-bit), `POSG` 10 rows
  (`PGST`, 16-bit), all in `LEAGUE.DAT` member 0 [M];
- **`PPRO`** in the dynasty template (`TEMPLATE.DAT` member 1), 4 fields — `PGID`,
  `PRWK` (5 bits), `PRPR` (8), `PRTY` (2) — capacity 75, **0 rows on the disc**:
  the per-player professional projection a dynasty accumulates [M].

Editing a draft class is therefore a *save* problem, not a disc problem, and this
module works off the disc. It is named here so nobody looks for it in a container.

---

## 10. What ports, lane by lane

For each Madden 09 lane, whether it runs on this disc with a schema table only,
needs a new field map, or has no NCAA equivalent [M].

| Madden 09 lane | on this disc | why |
|---|---|---|
| `textures.container_inventory` | **ports unchanged** | same `TERF` stack; 85/85 containers, 30,391/30,391 members |
| `players.team_databases` (catalogue half) | **ports unchanged** | 580/582 databases, 8,564/8,564 checksums |
| `players.team_databases` (writer half) | **a new field map, on the same base** | Madden's writes `PFNA`, `PLNA`, `PAGE` and 20 seven-bit ratings; this `PLAY` has none of the first three and its ratings are five bits. The *lane* ported: both games instantiate `_lanes/tdb_records.TdbRecordLane`, and what did not port is the field list — which is the point of the split |
| `identity.team_records` | **a different writer, on the same base** | Madden's writes `TDNA`/`TLNA`/`TSNA`/`TMNC` and six colour bytes; `TLNA`, `TMNC` and all six colour fields are absent here. NCAA's writes `TDNA`/`TMNA`/`TSNA` plus `CONF`, `DIVI`, `STAD` and `COCH` names, and offers no colour |
| `menus.text_members` (catalogue half) | **ports unchanged** | 1,247 `TEXT` members, 241,787 bytes |
| `menus.text_members` (writer half) | **ports unchanged, on the same base** | the `TEXT` format is identical; both games instantiate `_lanes/text_banks.TextBankLane`. What differs is which containers a cache names: three of this disc's four `TEXT` containers are named by none |
| `playbooks.databases` | **a new field map, on the same base** | 19 of 19 table names identical; `PBPL` has no `name` here, so the play name moves to `PLYL` and six other tables, and five widths shift. Written, on `TdbRecordLane` |
| `uniforms.mmap_export` / `uniforms.disc_art_writer` | **ports unchanged** | `MMAP` is the same format and the decoder is now in `_formats`; both games instantiate `_lanes/terf_art.TerfArtLane` and `TerfArtWriteLane` |
| `rosters.face_textures` | same | 64 player faces, 18 coach faces here against 4,611 members there |
| `field_art.textures`, `stadiums.textures`, `presentation.ui_textures` | same | the containers differ by name; the format does not |
| `audio.streams` | **ports as an exporter, not as a writer** | 412 of 8,021 streams are EA-XA; 7,609 are MicroTalk |
| `audio.banks` | **ports unchanged** | 728/728 banks, 1,213 sounds |
| `gameplay.executable_patches` | **no equivalent** | every patch site is per-title research; nothing found in `SLUS_217.70` applies to `SLUS_217.52` |

### The tables one disc has and the other does not [M]

| table | NCAA 09 | Madden 09 |
|---|---|---|
| `PACL` colour palette | `LEAGUE.DAT` member 0, **64 rows** | **absent** |
| `LTBL` | `LEAGUE.DAT` member 0, 28 rows | **absent** |
| `PNLU` | `LEAGUE.DAT` member 0, 58 rows | **absent** |
| `THST` | `LEAGUE.DAT` member 0, 38 rows | **absent** |
| `BOWL` | `LEAGUE.DAT` member 0, 37 rows | **absent** |
| `HEIS` | `TEMPLATE.DAT` member 1, 10 rows | **absent** |
| `PPRO` pro projection | `TEMPLATE.DAT` member 1, 0 rows | **absent** |
| `SLRI` salary cap | **absent** | `TEMPLATE.DAT`, 1 row |
| `UNIF` uniforms | **absent** | `TEMPLATE.DAT` member 7, **270 rows** |

`STAD`, `CONF` and `DIVI` exist on both, and *where* is the difference: NCAA 09
populates all three in its **league** database (242, 25 and 10 rows), while
Madden 09 has them only in `TEMPLATE.DAT` and with 50, 2 and 9 rows. A lane that
reads a league's stadiums or conferences has something to read here and nothing
there.

The absences run both ways and each is a fact about the sport. A college league
has no salary cap, so no `SLRI`; it has bowls, a Heisman and a colour palette, so
`BOWL`, `HEIS` and `PACL`; and it has no shipped uniform rows, so no `UNIF`.

---

## 11. What a writer for this disc still needs

Four of the six are now done; what is left is stated as plainly as what was.

1. **Field types 13 and 14 named**, or the two refused databases stay refused —
   and with them the only name pool on the disc (§7). **Still open.**
2. ~~**The scale of `PLAY`'s five-bit ratings** established from one record~~ —
   **done** (§2): the fields hold 0..31, every value is in use, and the editor's
   bound is the field's own rather than a 0–99 number nobody measured.
3. **The `TEAM` → `PACL` link** found, before any colour control exists (§3).
   **Still open**, and the identity writer ships without a colour control
   because of it.
4. ~~**A container writer for this disc**~~ — **done**: `ea_terf.rewrite_member`
   plus `_lanes/preload_coherence`, with the **three** `QL01` preload caches
   kept in step — NCAA 09 ships `FE.QKL`, `GAME.QKL` and `PL.QKL` where Madden 09
   ships two. Read by this module's own parser: **564 copy entries**, 81 of them
   a container's directory and 483 a member, naming 36, 27 and 9 containers
   respectively [M]. Every one is a byte copy of something already on the disc,
   so an edit that moves a member's stored size or codec moves the directory the
   caches carry, and a cache left stale hands the game the wrong offsets.
   `LEAGUE.DAT`'s members are `RLE1`, for which `ea_terf` already has an encoder;
   `UNIFORM.DAT`'s and `PLADATA.DAT`'s are `LZH1`, for which it now does too.
5. ~~**The four CRCs recomputed on every database write.**~~ — **done**:
   `ea_tdb.recompute_crcs` on every write and `ea_tdb.verify_crcs` from the
   destination's own bytes in the verifier. They were already proved correct on
   this disc's own bytes — 8,564 of 8,564 — before a writer existed, which is
   the order the Madden module used.
6. **A boot.** Nothing built from this disc has been run. This is the one that
   has not moved, and it is the one that decides whether any of the above is
   worth anything to a player.
