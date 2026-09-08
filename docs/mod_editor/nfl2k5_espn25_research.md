# ESPN 25th Anniversary research, 2026-09-07

EXPERIMENTAL / UNWITNESSED. M1 research decision, before implementation.
PROVED here means retail bytes and bounded native x86 execution with declared
file-I/O and presentation substitutes. It never means a played game.

## Roster mechanism: resolved

The 50 away/home selections use **35 shared historic ROST resources**, all in
pack `0`, outer entries 113..187. They do not use the current NFL team players.
There are 75 historic resources in the archive, each with 53 primary players,
zero secondary players, one team and the existing 84-byte player codec.

1. `20CB30` selects a SITU record using `2CFD40`. Fields +18/+20 select
   home name/year and +14/+1C select away name/year. The loader processes home
   first. `20C4E0` supplies the live team identity as a fallback and translates
   `oilers` to `titans` for that fallback only.
2. `20BD80` searches the main ROST root +58/+5C historical descriptors, count
   75, stride 16. A case-insensitive name match (`30CF0`) **and** matching u16
   year at descriptor +0 are required. The year is passed in EBX.
3. `2D17B0` formats `h-%s-%d-%s-%d.iff` using descriptor +4 (two UTF-16 team
   code characters), +0 (u16 year), +0C (name pointer), +2 (u8 kit suffix).
   The archive identity is CRC32 of the uppercase UTF-16LE filename. All 75
   generated identities match distinct retail ROST outer entries exactly.
4. The file loader `43F50` and `449E0` acquire the ROST named `historic`.
   `C1030` imports its one team into an available created/historic team slot
   in the live roster arena. It calls the real `C0500` relocator, copies each
   selected player through the team's pointer list, names, appearance, number,
   position and ratings. Rating bytes are clamped by the native importer to
   0..100. Original college values are indices into the main college table,
   not ordinary editable relative college pointers in these historic files.
5. `2D13B0` publishes the loaded team at `C8F158`; `2D1440` returns it.
   `77AE0`/`77B20` publish the home/away teams. SITU +58/+5C independently set
   the away/home uniform selection using `E30E0`/`E3000`. The descriptor's
   filename suffix is not a replacement for those uniform choices.

The bounded trace executes the real lookup, Unicode filename formatter,
historic importer, player allocation helpers and pointer relocators. Only the
archive open/wait/lookup/release calls are replaced with bounded reads of the
matching real resource. The selection trace also substitutes the controller,
weather setup and screen-transition boundaries; it does not render a kit.

Moment 0 loads home outer 133 (`h-10-1966-packers-3.iff`) and away outer 125
(`h-07-1971-cowboys-4.iff`). Native import gives two separate live teams with
53 player pointers each. All 50 native descriptor searches agree with the
independent host map. Full bindings are generated from the user's source by
the delivered inspector; no player content is supplied by this project.

## Field map

Offsets are within each 0x6C SITU record. Home is engine side 0, away side 1.
The two Boolean SITU side selectors use **1 = home, 0 = away**.

| Offset | Meaning / proof | Editing decision |
|---|---|---|
| 00,04,08,0C | Title, history, objective, date, existing text consumers | Existing fixed allocation writer |
| 10 | Main roster stadium **table index**, `20CC05..20CC2B`, not stadium ID | Existing valid stadium indices |
| 14,18 | Away/home selector names | Only a validated name/year pair |
| 1C,20 | Away/home historic roster years | Same pair, never display-only |
| 24 | Human-controlled side; `20CC59`, `27B32E`, completion `20C682` | 0 away, 1 home |
| 28 | Possession side; `10C1BC..10C228`, `10BD9E..10BDC5` | 0 away, 1 home |
| 2C,34 | Away/home starting scores; `10C1B9..10C1DF`, `10BD86..10BD9C`; also `D6323`/`250E1C` | Bounded scores |
| 30,38 | Historical final score text callbacks `2C5980`/`2C59B0` | Display values, not completion targets |
| 3C | Quarter index; UI `2C5AD0`, native `10BDF1` switch stores index +1 | Regulation 0..3 |
| 40 | Ball location in yards from midfield; native multiplies by 91.44; UI `2C5CA0` | Signed yards; positive is away half |
| 44 | Yards to first down; sign follows possession; `10C207..10C250` | Positive distance |
| 48 | Down state; UI `2C5BB0`, native `10BE95` switch: 0 kickoff, 1..4 down | 0..4 |
| 4C | Quarter clock in seconds; `2C5B40` minutes/remainder, `10BE48` clock store | Finite seconds |
| 50,54 | Away/home timeouts; `10C1C6/1DF`, `10BDD9..10BDEE` | 0..3 |
| 58,5C | Away/home uniform choices; `20CBF5..20CC00`; thumbnail callbacks `2C5DC0/2C5E30` | Retain source choices; assets need their own validation |
| 60 | Weather preset input to `E3150`, copied to `E601D0` | Preserve; complete enum not established |
| 64 | Time/environment input copied to `E60184` | Preserve; meaning not fully established |
| 68 | Signed temperature-like input, converted to float at `20CC46..20CC53` | Preserve; temperature units still a hypothesis |

Moment 0 native setup writes home score 14, away 17, three timeouts each,
quarter 4, clock 290 seconds, down 1 and home possession. Ball coordinate is
-1645.9200439453125 and first-down coordinate -731.52001953125, matching
source -18 yards and 10 yards to gain times native 91.44.

`20C670` records completion when the human side wins the final score comparison
in mode 8 with the ordinary scenario flag. It does not inspect the prose
objective or the two historical final score fields. Broader game-end triggering
and reward presentation remain unwitnessed.

## Count growth: conditional feasibility, no install authorization from proof

| Component | Verdict |
|---|---|
| `165EE0` walker and related registration callbacks | Descriptor-driven count, stride 0x6C, no constant 25 |
| `2CFC40` / `2CFCA0` | Six field-relative pointer fixups and inverse, unchanged for more records |
| `166000` | Registers SITU callbacks/FourCC; no scenario limit |
| `2CFD00` | Stores descriptor count at C8F0D8, records base at C8F0D4 |
| `2CFD40` | Stride and non-null-base check only, **no bounds check** |
| Menu count `20C340` | Hard-coded `mov eax,25; ret`; callback pointer at 529660 |
| Caption `20C350`, display `20C800`, selection `20CB30` | Index-based; no local 25 bound; full list paging remains to be established |
| Completion `20C390` and `20C695` | 32-bit shift/mask at BF18CC; index 32 aliases index 0 |
| Profile `196DC0`/`196DD0` | Read/write full dword at profile +125C; **serialization/persistence of extra bits not proved** |
| Reward `20C2BC..20C2E2` | Hard-coded 25-iteration mask then reward ID 14; must change in concert with count |
| SITU storage | First uncompressed chunk of outer 22, not the entire outer entry |

SITU wrapper +4 is 0x71B0 bytes, wrapper +8 is **record count 25**, not body
memory size. The complete outer 22 is 128,976 bytes; other resources follow
the first 29,136-byte wrapped SITU. A growth writer must preserve those siblings,
rebuild the collection and use the existing transactional archive/XDVDFS writer.
Compressed siblings must retain their wrappers, including +14; any future
recompression must use `nfl_vc_lz_fill`. The current SITU and historic ROSTs
are uncompressed, so fixed-span edits require no recompression.

Design for 30: retain original ordinals 0..24, append five 108-byte records,
place the string pool after the extended table and recalculate all six biased
pointers for every record. Rebuild the descriptor and wrapper count together.
Patch the complete pinned menu-count and reward-loop spans only after UI paging
and saved completion bits 25..29 have been proved. No new code/data allocation
appears necessary for this 30-record design. More than 32 needs a versioned save
representation and audited readers; an XBE-only variable cannot provide it.

**Decision:** deliver a bounded 30-record authoring/relocation experiment and
fixed-25 editing. Refuse installation of expanded tables. Do not change existing
profiles or silently clear their high bits. The raw dword setters prove neither
their serialized location nor migration safety. The missing witness must save
and reload a new and an existing profile after completing moments 26 and 30,
verify all previous completion bits, rewards and other profile state, and cover
menu paging, re-entry and each new row. No console/emulator is permitted in this
session, so that part stops at the documented design as the brief requires.

## Editor decision

Use the existing RosterDocument and CSV codec, with a new hostable panel in the
Rosters tab. Select moment and side, show the bound historic resource, list all
other moments using it, and edit its existing 53 players. Every roster import
must explicitly acknowledge shared historic use. It also affects that historic
team outside Anniversary mode. Never label these shared files as private
per-moment pools. Changes stay in the bounded resource; unknown layouts refuse.

Independent rosters for two moments sharing one historic file need cloned ROST
resources, distinct selectors and appended 16-byte historical descriptors in
the main roster. The native filename format already supports such names, but
that requires main-ROST descriptor/string growth, new archive entries and a
proved fallback identity. This session does not invent an extra descriptor or
claim a selector rewrite alone clones the roster. A shared-resource editor is
the smallest supported implementation. Noah supplies historical player content.

Inputs were read-only. No network, game, display, audio or full-disc build was
used. Scratch reads were individually bounded; no archive pack was loaded in
RAM. The existing RC85 changelog and report index informed the storage,
allocator, resource-writer and roster compatibility decisions.
