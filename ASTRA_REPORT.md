# College checker research and beta-64 core

2026-09-09. Branch `local/hf63-college-checker`; starting commit
`8eccd7c79dc20fefb0f4e3190b7e75d6bf184537` on beta-63.1. The specific
`ASTRA_BRIEF.md` authorizes beta-64 research/core work despite the older shared
hotfix-only template in `HOTFIX_CONTEXT.md`. No questions were needed.

## Delivered and deliberately bounded

Implemented `mod_editor/core/nfl2k5_college_check.py`: a read-only scanner and
an in-memory, atomic repair for the main disc ROST, Xbox roster SAVEGAME.DAT,
and franchise SAVEGAME.DAT. Both player pools are scanned. Each finding/repair
names the source, player, pool, index, absolute byte offset, original raw word,
resolved target, reason, and static display inference. Repair changes only the
four bytes at each affected player's `+0x00`; the returned receipt includes
before/after hashes and every repaired record. Repetition is a no-op.

The core accepts bounded v0/v17 layouts and the studio's v1/v18 grown arenas.
It independently locates the tables so an invalid player reference cannot
prevent inspection. Candidate repairs must pass the unchanged strict codec;
an inline MyCareer footer must still match MyPlayer's identity. No validator
strictness, existing writer, GUI panel, Build preset, executable, manifest,
signature policy, or release allowlist was changed. `WIRING.md` describes the
protected page/export/packaging changes needed before this becomes a beta-64
button. This branch does not ship that button.

**Repair policy:** first `None` college (case-insensitive), otherwise the first
blank college, otherwise table entry zero. The caller can explicitly select a
different valid ordinal. The scanner reports null player pointers as *missing*,
not as a codec refusal; a valid None/blank college is clean. Nearest-address or
nearest-text repair is not implemented: it cannot establish the intended
college. Broken college-name records are reported, including every affected
player, but are not rewritten. Missing/overlapping/unbounded tables and
single-team resources without a local table are refused explicitly. Those
cases cannot be repaired under the player-four-bytes-only contract.

## 1. Byte map and formats

All words below are little-endian. For a nonzero serialized pointer word `w`
at absolute file offset `f`, `target = f + signed32(w) - 1`; zero means null.
Writing a pointer uses `signed32(target - f + 1)`. Do not interpret this word
as a college index in a main roster or save.

| Location | Meaning |
|---|---|
| Inner preamble `+0x0C` / `+0x10` / `+0x14` | `ROST` / version / relative root pointer |
| v17/v18 root | Inner preamble `+0x40` |
| v0/v1 root | Inner preamble `+0x20` |
| Root `+0x00/+0x04` | Primary player count / pointer, stride `0x54` |
| Root `+0x08/+0x0C` | Secondary/template count / pointer, stride `0x54` |
| Root `+0x20/+0x24` | College count / pointer, stride 8 |
| Player `+0x00` | Relative pointer to an 8-byte college record |
| College record `+0x00` | Relative pointer to a terminated UTF-16LE name, or null |
| College record `+0x04` | Stored metadata ID; **not necessarily the table ordinal** |
| Player `+0x10/+0x14/+0x2C` | First name / last name / history pointers; repair never writes them |
| Optional outer wrapper | `ROST`, declared inner length at `+4`; inner preamble follows 32 bytes later |

Main disc: pack `vc_53450030/0`, outer entry 5; resource is `0x90F80` bytes,
body `0x90F60`, root body `0x40`. Retail college table body `0xA758` has 266
records. Primary table body `0xAFA8` has 2,479 players; secondary pool has 68.
The retail **None** entry is ordinal **187**, record `0xAD30`, name `0x7B05C`,
stored ID **320**. Treating ID 320 as an out-of-count ordinal would falsely
flag a valid retail college. The checker preserves this metadata.

The common Xbox save envelope has wrapper `0x2E0`, inner preamble `0x300`,
root `0x320`, declared inner length `0x91020`, end of arena `0x91320`.
Franchise saves are 720,044 bytes and continue with season/front-office data;
the college pointers are still relative to their own fields. Source format
comes from framing, not a filename or total-size guess. Wrapped smaller
synthetic resources are supported, as are exact known bare sizes.

Grown v1/v18 arenas have root-relative size `0x92000`; their reserve block at
root `+0x91C00` is excluded from college targets and string scans. All trailing
season, front-office, reserve and career bytes remain unchanged by repair.

Historical/ESPN Anniversary and exported team resources are different:
player `+0x00` stores a signed main-table **ordinal**, often with no local
college table. Zero means main-table entry zero, not null; `-1` represents an
absent/invalid source college on native team export. `nfl2k5_espn25_rosters.py`
already writes ordinals intentionally. This checker will not reinterpret that
ABI as main-roster pointers. An integer mistakenly stored in a *main* roster's
pointer field is reported as the pointer it actually encodes, without guessing
which college the author meant.

The `.ROS` example in the brief needs a format qualification. NFL 2K5's
`SaveContainer` reads a directory/zip/loose `SAVEGAME.DAT` plus `EXTRA`.
The two `Roster.ROS` files found in the supplied hub are under Xbox 360 title
`54540807`, the APF lane, not NFL 2K5 title `53450030`. The examined file is
2,715,908 bytes; NFL 2K5's loader correctly refuses it with
`no SAVEGAME.DAT in <path>`. No authentic standalone NFL 2K5 roster save was
found in the supplied fixture directory or current qcow2; roster-save behavior
is exercised with generated v0 fixtures. This is not evidence of a college bug
in APF, and no APF format handling was added.

## 2. Native consumers and writers: static evidence

Read-only Ghidra corpus root:
`/media/noah/Storage/for codex 1.0/research/functions/nfl2k5/pseudo_c/`.
Missing small functions were examined with Capstone over the extracted retail
`default.xbe`. No game execution was used for these conclusions.

| Native function | Evidence and consequence |
|---|---|
| `0xC0500` / `0xC0730` | Root/table relocation and inverse serialization; see `shard_003584_004095.c:9881/10022`. They do not validate semantic college membership. |
| `0xE5E70` / `0xE5EB0` | Relocate/serialize the player's four pointer fields, preserving zero; `shard_004608_005119.c:2154/2188`. A nonzero bad college can travel through this arithmetic unchanged in meaning. |
| `0x2421D0` / `0x2421E0` | Relocate/serialize college-name pointer, preserving zero; `shard_009728_010239.c:16398` onward. |
| `0x320760` -> `0x145D90` | Player-card COLLEGE line; `shard_012800_013311.c:25020` and `shard_006144_006655.c:11113`. The getter **checks the player college pointer for null**, then reads the college record's first word. Renderer skips the value when the getter returns zero. Null player or null name therefore has a static blank-value path. Nonnull off-table targets are not membership-checked. |
| `0x3461F0` -> `0xC0A80` | Create Player obtains/reinitializes a created slot; `shard_013312_013823.c:13925` and `shard_003584_004095.c:10315`. Initialization chooses a random ordinal modulo 101 and bounds it against the table count, otherwise writes null. |
| `0x343CC0` / `0x343CE0` | Retail disassembly: pass current college to `0x2421F0` / `0x242240`, then write the returned pointer to player `+0x00`. Both next/previous selectors bound the resulting ordinal. |
| `0x242190` | Lookup returns ordinal of an exact college-record pointer, otherwise zero. Its use here is the college selector, not proof of team-export behavior. |
| `0xE6780` | Rookie generation selects from college bands, checks the resulting ordinal, then writes `table + ordinal*8` or null; `shard_004608_005119.c:3218–3251`. A normal retail table has enough entries for these bands. An undersized edited table is a separate native edge case, not proof that every malformed table is safe. |
| `0xC0FA0` | Native single-team exporter, disassembled `0xC0FD9–0xC0FF1`: null -> `-1`; otherwise `(pointer-table)>>3`, signed/range checked, invalid -> `-1`. It **does not check eight-byte alignment**, so a pointer inside a record rounds down to that ordinal. After serialization it replaces exported player `+0x00` words with these ordinals at `0xC1010–0xC101E`. |
| `0xC1030` | Team import saves ordinal words before relocation, then at the end maps `-1`, negative or `>=count` to null; valid ordinal -> local `table+ordinal*8`. See `shard_003584_004095.c:10577` and `:11078–11094`. |

**Correction to the earlier schedule report and existing codec comment:**
`0x242190`'s zero fallback is not the native team export result. The exporter
actually uses `-1` for null/out-of-table, and an in-table misalignment can round
down. Likewise, the card getter does check null. Existing code was not modified
just to rewrite these research comments; this report supersedes those two
claims. Neither difference changes the proved 63.1 schedule fix.

For nonnull off-table, out-of-arena, or malformed name targets, the exact game
text is **unknown**. The first word at that target is used as a runtime string
pointer; following arbitrary bytes could show unrelated text or fail. The
scanner never fabricates the result by treating a string as a college record.
A college-name pointer into a readable string suffix cannot be distinguished
from deliberate string sharing without external provenance; it is not labeled
corrupt solely because another string starts earlier.

## 3. Studio refusal map on the starting beta-63.1 code

| Entry/operation | Behavior and source |
|---|---|
| `SaveContainer.load` | Signature/container gates run before parsing; `nfl2k5_roster_records.py:2630`. Missing EXTRA or mismatch is a separate refusal and remains unchanged. |
| Rosters disc/save load | `RosterEditorPanel.load_disc/load_save`, `:1946/:1960`, calls `RosterDocument` through `rr.load_image`/`container.document`. Legacy v0/v17 `_parse` at `rr:1465–1483/:1586–1588` maps any non-table player target to blank without dereferencing it. Null also displays blank. |
| College table/name load | The legacy document follows each college record/name pointer: an out-of-file name raises `string offset 0x... is outside the body` at `rr:1286`; out-of-file college table can raise `struct.error`. It tolerates null names, unaligned text, replacement-decoded invalid UTF-16, counts above 4000 (ignored table), and some suffix reads. |
| v1/v18 load, or reserve-owned document | `rr:1436–1440/:1590–1595` invokes strict decode/ownership validation, so an out-of-arena player college can refuse **load**, unlike legacy v0/v17. |
| Strict ROST decode | `nfl2k5_save_rost.py:168–216`: bounded tables, every college name validated, both player pools validated. Null accepted. In-arena off-table accepted and recorded in `unresolved_colleges`. Out-of-arena refused with player pool/index/offset. |
| Typed player edits / serialization | `SaveRost.edit_player` refuses pointer-field edits: `college_pointer: pointer edits require a typed relocation writer`; `to_bytes` refuses `college_pointer: direct pointer mutation refused` (`:289–319`). `RosterDocument.to_body`, by contrast, encodes its record values directly. |
| Rosters validator cards | `rr.validate` at `:3868` checks fields/membership/name pool, **not college validity**. A blank displayed college does not by itself generate a college error. |
| Existing college edit | `rr.set_college` at `:1737` checks ordinal bounds and writes a local relative pointer. Invalid choice: `college index N is outside 0..M`. `RosterEditorPanel._college_chosen` uses that typed setter. Choosing a valid table entry can already repair an isolated player pointer in a document that loaded. |
| CSV/JSON college text | CSV `rr:3195–3199`: unknown text is logged with `'X' is not one of the roster's N colleges`. JSON `apply_body`, `rr:2884–2888`, logs `'X' is not one of this roster's colleges`; invalid field is skipped. Raw pointer imports are skipped with `college_pointer is a pointer and cannot travel between roster copies`. These are edit-level messages, not automatic whole-build failures. |
| Roster-save signed copy | `rr.save_document`, `:2742–2753`: depth check -> `to_body` -> `ps.validate_save` -> container write. Thus legacy load/rating edit can succeed and save can still refuse the college. |
| Ownership-changing operations | `nfl2k5_practice_squad.validate_save/validate_roster`, `:309/:177`, calls strict decode. Promotions/demotions, salary recomputation and other callers inherit the codec refusal; the college is not an ownership error itself. |
| Franchise load | `FranchiseSave.__init__`, `:340`, checks envelope and parses roster lazily. Page load still needs a roster document. `FranchisePanel.load`, `:554`, adopts it. |
| Franchise edit/copy | `ps.validate_save_edit`, `:318`, skips the codec only when arena **and IR** bytes are unchanged. `RosterEditorPanel._franchise_edit` `:1476`, `FranchisePanel.push/_rebuild` `:630/:651`, and `FranchiseSave.write` `:404` use this boundary. Schedule/year/cap/control-only edits can pass despite a bad player pointer; a rating/roster change still invokes strict decode. Final copy also reconstructs `RosterDocument` and checks depth, so this is not a general table-corruption bypass. |
| Disc Build & Share | `mod_build.py:1564–1583` delegates to `rr.apply` -> `apply_body`; basic field replay preserves a preexisting invalid player pointer. It is not a college repair or comprehensive college validator. Table parse failures can make roster status foreign or abort the pass. Other selected build passes can add their own strict roster gates. |
| Read-only audit tool | `tools/nfl_roster.py:132/:155/:389–395` is stricter: non-table player target -> `outer 5 primary_players N: college pointer 0x... does not select an 0x08-byte college record`; out-of-body pointers, unaligned/unterminated/nonprintable/invalid UTF-16 also refuse. This CLI parser was not loosened by 63.1 and is not the Rosters page's parser. |
| Inline MyCareer | `nfl2k5_my_career_save.read`, `:91–107`, checks copied root-relative college/first/last identity at footer `+44/+48/+52`; mismatch -> `MyPlayer name or college reference changed`. Footer format/range/checksum validation also remains strict. Legacy external checkpoints store college at state `+84` and recipe `+96`; they are outside this payload-only repair. |

Root cause of the reported *class* of refusals: legacy document parsing and
save validation have different contracts. The editor can represent an unknown
college as blank; the save writer's arena-bounds gate still refuses it. Neither
zero nor a valid None/blank table entry is itself a 63.1 save refusal. The
tester's actual offending bytes were not supplied, so their specific cause
cannot be assigned to null, an outside pointer, or a broken college table.

## 4. Reproductions and real-input evidence

Generated franchise: player 0 at `0xB288`, colleges `0xAA38`, count 5.
The following mutations were reproduced through legacy document, codec and
`validate_save`; core repair then passed the unchanged validators.

| Mutation at player `+0x00` | Raw word | 63.1 legacy load / strict save validation |
|---|---|---|
| Null | `00000000` | Blank / accepted |
| Arena end +16 | `000860A9` | Blank / refused |
| Target -4 | `FFFF4D75` | Blank / refused |
| First college +1 | `FFFFF7B2` | Blank / accepted, unresolved |
| One record beyond table | `FFFFF7D9` | Blank / accepted, unresolved |
| Directly to college name string | `0006EFB5` | Blank / accepted, unresolved |
| Two bytes inside that string | `0006EFB7` | Blank / accepted, unresolved |

Exact outside refusal:

```text
no supported ROST: primary player 0 at 0xB288: college pointer: range outside ROST arena data
```

Separate table mutations produced these exact codec suffixes (each prefixed
`no supported ROST: `):

| Mutation | Refusal |
|---|---|
| Name outside arena, including a readable franchise suffix | `UTF-16 pointer: range outside ROST arena data` |
| Odd name target | `unaligned UTF-16 string` |
| No terminator before arena end | `unterminated UTF-16 string` |
| Lone UTF-16 high surrogate | `invalid UTF-16 string` |
| College count 4001 | `colleges: implausible count 4001` |
| Null table with count 5 | `colleges: null table with nonzero count` |
| Table outside payload | `colleges: range outside ROST arena data` |

Legacy document accepted all these except the out-of-file table; it raised
`unpack_from requires a buffer of at least 720148 bytes for unpacking 4 bytes
at offset 720144 (actual buffer size is 720044)`. A name target outside the
whole file separately raised `string offset 0xafd10 is outside the body`.
The page presents `Could not read the save: RosterRecordError: ...` for the
latter. A null name pointer and an aligned interior name suffix both load and
decode; neither is automatically treated as a broken college table.

Offscreen real `RosterEditorPanel` reproductions:

* Roster v0 save: null/off-table college -> rating edit -> signed copy succeeds.
  Outside college -> load succeeds -> rating edit -> signed copy refuses.
  New core repair + `adopt_body` -> signed copy succeeds with rating retained.
* Franchise: outside college -> schedule edit and schedule-only signed copy
  succeed. Add a player rating edit -> copy refuses. Repair -> copy succeeds.
* Out-of-file college **name** -> page load fails; raw scanner still reports
  the bad table entry and all three synthetic players referencing it.
* v1/v18: bad pointer into the reserve tail refuses document load; scanner
  reports it and repair restores the exact original bytes, including the tail.

All retail/source inputs were opened read-only; no retail bytes were copied
into the repository or fixtures. The new tests mutate only memory copies.

| Input | Players | Findings / table issues | SHA-256 |
|---|---:|---|---|
| Retail outer-5 body | 2547 | 0 / 0 | `b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae` |
| Hub `f0/.../SAVEGAME.DAT` | 2547 | 0 / 0 | `56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8` |
| Hub `f1/.../SAVEGAME.DAT` | 2547 | 0 / 0 | `255da39178695a69c01efad9237764cbbd88c63aa78cfe911c8e3b070b6215ed` |
| Hub `256B40374FD6-Franchise1/.../SAVEGAME.DAT` | 2547 | 0 / 0 | `0db746fe2c8ae2102fdd420863a5e5bcddec4b83ac3e234568824c337e4422a7` |
| qcow2 `MyNFL1` | 2547 | 0 / 0 | `0cfdf173c43d32569f12c730e6e3e97df1b1b9e877c0097be0d915ef2c407f3b` |

Hub base: `/home/noah/Desktop/2K5-8 Editors/save_fixtures/`. Current qcow2:
`/home/noah/.var/app/app.xemu.xemu/data/xemu/xemu/xbox_hdd.qcow2`, read directly
with `tools.nfl2k5_xemu_saves.scan_image`, no extraction or emulator launch.
It also contains the identical Franchise1, five TMM team saves, a profile and
settings; no standalone roster save. Every listed franchise signature verified,
`validate_save` passed, and `RosterDocument.to_body()` was byte-identical.
Three hub saves additionally passed in-memory null/outside/misaligned/string
fault insertion and repair, with original files rechecked unchanged. This
reproduces the failure mechanism on real layouts, not a naturally corrupt
community save that was never provided.

## 5. Provenance and writer audit

* **Native Create Player / rookie generation:** the examined writers choose a
  bounded local table entry or null. The card's null path is defined. No
  evidence here that leaving the college blank naturally creates an outside
  pointer on a retail table.
* **Community files / Flying Finn:** the local research at
  `research/flying-finn/REPORT.md` describes college editing and `.PlayerData`
  backup data, but does not supply a college-corrupt source/output pair. The
  Finn-related `f0/f1` saves both have zero findings. Do not attribute this bug
  to Finn or a specific community author. Copying raw records between address
  layouts without relocating pointers could produce it; that is a mechanism,
  not a demonstrated provenance for the tester's file.
* **ESPN Anniversary:** `nfl2k5_espn25_rosters.compile_resource`, `:288–341`,
  requires the historical resource shape and exact college-name membership,
  then intentionally writes the main-table ordinal. Treating those words as
  malformed main-roster pointers would itself be a checker bug.
* **Studio typed college paths:** `set_college`, CSV, JSON replay, draft-start
  creation and save-to-disc export resolve against the destination table.
  `.PlayerData` import skips raw pointer fields and applies recognized college
  text; unknown text is logged and the old college remains (`rr:3546–3588`).
  Copy/Paste excludes college; CAP templates only change ratings. These paths
  do not invent an outside reference from a valid table. They can preserve
  preexisting anomalies; a typed setter cannot repair an unreadable table.
* **Studio raw API:** `PlayerRecord.set('college_pointer', ...)` and direct
  record mutation **can** create a bad reference, and `RosterDocument.to_body`
  serializes it. A regression demonstrates `0x7FFFFFFF` becoming a strict
  codec refusal. It would be inaccurate to claim that no studio API can
  produce one. The typed `SaveRost` editor and transferable edits refuse this
  raw operation. No validator was broadened to hide that difference.
* **Arena migration:** `nfl2k5_roster_arena.pointer_fields/migrate`, `:126–198`,
  enumerates and relocates college/name/player pointers with their records,
  using validated layouts. It preserves in-arena unknown targets as such;
  outside references are refused by decode. It does not infer colleges.
* **Progression/aging:** the studio's age/year/history passes do not own college
  words. Native serialization preserves references, and rookie generation
  explicitly replaces college from the table. No spontaneous deterioration
  was observed in the four distinct saves, including the year-7 pair. That
  is not exhaustive proof of every native season transition or imported mod.
* **Career identity copies:** inline footer checks now guard candidate repair;
  legacy external checkpoint state is outside the supplied save bytes. The
  checker never reseals a different identity or edits an external checkpoint.

## 6. Verification and limits

Red run before creating the core: the existing-boundary reproduction passed;
eight new core-dependent tests failed because `nfl2k5_college_check` did not
exist (`Ran 9 tests ... FAILED (errors=8)`). This is a new repair capability,
not a relaxation intended to turn existing refusal tests green. During the
writer audit, the inline-career regression independently failed with
`AssertionError: CollegeCheckError not raised`; the candidate identity guard
then made it pass.

Standalone validation, `PYTHONPATH=.` and `QT_QPA_PLATFORM=offscreen` for Qt:

| Command (`python3 tests/mod_editor/…`) | Result |
|---|---|
| `test_nfl2k5_college_check.py` | 17 tests, OK; synthetic matrices and available retail/private gates ran |
| `test_nfl2k5_college_check_qt.py` | 3 tests, OK |
| `test_nfl2k5_save_rost.py` | 9 tests, OK |
| `test_nfl2k5_roster_records.py` | 108 tests, OK |
| `test_nfl2k5_franchise_save.py` | 13 tests, OK |
| `test_nfl2k5_franchise_schedule_college.py` | 8 tests, OK |
| `test_nfl2k5_practice_squad.py` | 27 tests, OK |

185 tests total, no skips on this machine. New retail gates use precise
`SkipTest` messages when the private input is absent. Tests prove source
immutability, exact allowed byte differences, idempotence, multiple affected
players/pools, default/explicit choices, stale hashes, structural bounds,
ambiguous framing, invalid names, unrelated-history refusal, reserved-tail and
franchise-suffix preservation, metadata preservation, signed-copy read-back,
and inline-career identity consistency. GUI tests exercise current pages,
not the proposed future action.

`python3 packaging/repin.py` reported `would apply 0 pin update(s)`;
`python3 packaging/repin.py --apply` reported `applied 0 pin update(s)`.
`py_compile` for the three new Python files and `git diff --cached --check`
also passed. No existing pinned writer was changed. The new module has no XBE writes, so the cave/memory
writer gates and manifest regeneration do not apply. The release allowlist
addition remains explicitly in WIRING for beta 64. No full-disc build, emulator,
visible GUI, or audio was run; no in-game outcome is claimed.

Noah's eventual witness: open a copy of the actual reported failing save,
inspect the college line before/after, choose the intended college (or None),
save/reload in game, and verify one roster edit plus the schedule edit. Also
check a created player with a blank college, a draft prospect, and a historical
team separately. A malformed table needs an actual specimen before expanding
repair ownership beyond player words. No tester input is required to use or
review the bounded core delivered here.

## 7. Relay draft for BigTimeEmpire (not sent)

> 63.1 fixes the franchise schedule refusal caused by a college pointer that
> stays inside the roster arena but misses the college table, and schedule-only
> edits no longer depend on roster validation. A blank college by itself is
> already accepted. For beta 64, the checker/repair core is implemented: it can
> identify each missing or invalid player college reference and point it to a
> valid college, normally None, while preserving the rest of the player/save
> data. The Rosters button still needs integration and in-game testing. Broken
> college tables will be identified rather than automatically guessed at.

## Delivery

Commit only these explicit paths on this branch: `ASTRA_REPORT.md`, `WIRING.md`,
`mod_editor/core/nfl2k5_college_check.py`,
`tests/mod_editor/test_nfl2k5_college_check.py`, and
`tests/mod_editor/test_nfl2k5_college_check_qt.py`. The supplied untracked
`ASTRA_BRIEF.md` and `HOTFIX_CONTEXT.md` remain untouched as task inputs. No push.
