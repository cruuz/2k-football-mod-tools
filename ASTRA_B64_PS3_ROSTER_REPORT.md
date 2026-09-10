# Beta 64: the 1993 NFL Season PS3 roster as an Xbox 360 roster save (2026-09-09)

Branch `astra/b64-ps3-roster` (from `local/stack-beta-64`). Written by Claude Fable 5.1 acting
as the Astra role. Everything below is proved offline from the files themselves; nothing has been
loaded in Xenia or on a console. Every in-game statement is labelled UNWITNESSED.

## What shipped

| Path | Role |
| --- | --- |
| `mod_editor/apf_studio/ps3_roster_convert.py` | Core converter: structure inventory, platform detection, conversion, strict reparse gate, file writer with receipt, CLI |
| `mod_editor/apf_studio/ps3_roster_import_qt.py` | `Ps3RosterImportPanel`: "Choose PS3 roster..." / "Import PS3 roster..." with a counted receipt dialog and the UNWITNESSED status |
| `tests/mod_editor/test_apf_ps3_roster_convert.py` | 11 tests: synthetic PS3-style fixture rendered as input and as the exact expected Xbox output, file/zip contract, retail-gated 1993 member |
| `tests/mod_editor/test_apf_ps3_roster_import_qt.py` | 2 offscreen panel tests |
| `reports/ps3_import/roster_convert_receipt.json` | The receipt of converting the real member (counts, offsets, hashes; no roster text) |
| `WIRING.md` (top section) | The protected hookups: gui.py tab, allowlist, runtime closure, registry row |

Run: `cd <worktree> && PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_ps3_roster_convert.py -v`
(the retail class skips precisely when `/home/noah/Downloads/1993 NFL Season (Update Logos).zip` is absent or
its member hash differs) and `... python3 tests/mod_editor/test_apf_ps3_roster_import_qt.py -v`.

CLI: `python3 -m mod_editor.apf_studio.ps3_roster_convert "<zip or USERDATA>" <new.ROS> [--member ...] [--receipt ...]`
picks the one `*-ROS/USERDATA` member of the ZIP itself.

## Inputs (read-only, never copied into the repo)

* PS3 roster: member `1993 NFL Season (Update Logos)/BLUS30049-ROS/USERDATA` of the ZIP, 2,715,908 B,
  sha256 `0b3b24f2c14f3770a6728dce1560e6534e8803d966a264ff1eaace632c44a934`, file date 2026-09-03.
  The same folder holds `USERDATA.bak1` (2019-02-08), which turned out to be the **stock** roster:
  byte-identical to the Xbox fixture across the whole string pool (36,140/36,140 and 81,064/81,064
  bytes in the two name regions) and containing zero odd pointers. It is the same-content pair that
  isolates the pure platform differences.
* Xbox 360 fixtures: `/home/noah/Downloads/apfe/Roster.ROS` and `Roster2.ROS` (Urianus, identical
  except two bytes at 0x0B815A).

## The pointer rule, proved from all the data

Every pointer in the roster is `target = field + stored - 1` on both platforms. The claim is not from one
sample:

1. **Pointer-column census.** For every root table (strides derived from the contiguous root table:
   players 332, teams 384, colleges 8, staff 180, table 10 188, labels 12, name pools 8/8, config 152,
   table 20 152, table 21 32, cities 120) every 4-byte column was tested on the Xbox fixture. A column is
   a string-pointer column only if 100% of its non-null rows resolve to an even, non-nested, printable
   UTF-16BE string in the pool. Result: 44 columns in 13 tables carry **42,825** string references to
   **6,368** allocations on Xbox. False positives were caught and excluded by that rule: palette +0x2C
   (the 8 selector bytes) and table 21 +0x10 merely resolve into the pool by chance, and `stored == 0`
   resolves to `field - 1` (why table 10 +0x94 looked self-referential).
2. **Same rule on PS3.** All 42,825 references resolve inside the file with the same formula; last/first
   names decode at even targets identically to Xbox for stock players (24,565 of the first 24,576 pool
   bytes are identical). So there is no +1/-1 bias and no byte-string grammar: PS3 strings are UTF-16BE
   with the same self-relative pointer.
3. **What is actually wrong.** 1,647 references (1,344 nicknames, 128 team strings for 32 teams, 64 staff,
   14 colleges, 32 config names, 28 table-21, 15 city fields) resolve to **208 odd allocations** that lie in
   **six gapless runs** (2,602 B) the 2026 editor pass wrote one byte early: the text itself sits at odd
   offsets (`00 54 00 6F 00 6F ...` = "Too Tall" from 0x207A9F). For ASCII, "BE at odd" and "LE at even
   with +1 bias" read the same, but the stock 2019 PS3 backup has 0 odd pointers, so this is editor damage,
   not a PS3 build quirk. 1,333 of the nickname references share one odd empty string; only 11 players carry
   a real nickname.
4. **Stale references.** The same editor rewrote the pool without repointing 983 references whose stored
   values still equal the 2019 stock file: name pools t12/t13 (650 + 1,050 rows, 475 now read suffixes such
   as "ian", "e"), accolade/biography fields of 271 players (101 on team rosters), and 76 references that read
   misaligned garbage (U+xx00 code points) across the editor's odd strings. Neither the Xbox fixture nor the
   stock PS3 file contains a single nested allocation, so nesting is damage by definition.

## The platform delta, proved from the stock pair

Diffing the stock PS3 backup against `Roster.ROS` and excluding Urianus' content tables leaves exactly:

| Class | Bytes | PS3 | Xbox 360 | Converter |
| --- | --- | --- | --- | --- |
| Root pointer fields 15..18 | 16 | self-relative to external runtime tables | raw runtime addresses `0xA3E7FD5C + file offset of the table` (the four deltas are the table sizes 532 / 12,768 / 29,792 B) | writes the rule; reproduces the fixture's four words exactly |
| Palette colours, 266 x 10 | 10,640 | `RR GG BB FF` (2,660/2,660) | `FF RR GG BB` (2,660/2,660); 2,298 triplets identical after rotation, `edb01d` and `8d8d8d` shared | rotates every colour |
| Runtime block after the pool at 0x230224 | 32 | 8 PS3 addresses/words | 8 Xbox words, constant across both fixtures | writes the Xbox words |
| User-book bank headers (5 x `BLPS` at 0x26FA70 + k x 32,288, plus the truncated 6th header at file end) | 64 | `32BC8580 / 30E25303 / 10E25303` | `A72720A0 / A0E35203 / 80E35203` | writes the Xbox words |
| Table 15 row 265 byte 1 | 1 | 0 | 1 | left alone (content: Urianus' last custom palette flag) |

Nothing else differs structurally: the player record, teams, selectors, config, labels and user playbook
slots have the same encoding on both platforms (a byte-column invariant sweep over every table found no
other constant/disjoint columns).

## What the converter does (and the reparse gate)

1. Inventory all 44 string columns; classify every allocation: odd, nested (parity-aware: when an outer
   read is garbage across a clean inner string the outer is stale, otherwise the inner suffix is; empty
   allocations never enclose), below the pool (3 refs into the zeroed reserved area), garbage-reading
   (5 allocations, 9 refs), empty.
2. Canonicalise every empty/stale/garbage/below-pool reference to the one shared empty string the game's own
   serialiser interns (0x1F5750; Xbox has exactly one empty allocation with 25,842 refs, stock PS3 one with
   26,013, the 2026 file 1,022). 3,655 empty and 1,010 stale references were repointed.
3. Shift each gapless odd run one byte earlier when the guard byte before it is a free zero and the first
   byte is the zero high byte (all 5 live runs, 2,600 B); otherwise relocate into free even pool space
   (exercised by the synthetic test, 0 relocations on the real file). Repoint 314 odd references.
4. Rotate 2,660 palette colours; write the 4 root words, the 8-word block and the 16 bank words.
5. Byte accounting: every changed byte must lie in a declared span (24,527 bytes changed; 10,597 in player
   pointer fields, 8,388 palette, 3,042 other-table pointer fields, 1,338 pool bytes, 221 team fields,
   198 config fields, 16 root, 29 runtime block, 54 bank headers).
6. Reparse gate on the output: `save_roster_players.inspect_bytes` (2,254 players, every text field decoded,
   1,680 memberships, 3,869 text allocations), `apf_save_playbook_assignments.parse_save` (69 labels),
   `apf_save_custom_team_appearance._table_layout` plus strict decoding of all 160 team strings, the
   converter's own inventory (0 odd, 0 nested, 0 garbage, no overlaps), platform re-detected as Xbox 360 and
   the root rule re-verified. `write_conversion` re-reads the file from disk and runs the gate again.
   The custom-team appearance `parse_save` is recorded, not gated: it refuses this roster for a content
   reason ("team slot 36 is not a user-team record": the 1993 roster gives teams 0-3 and 32-35 category 2 and
   36-39 category 0); on the untouched PS3 file it fails earlier with "user slot 32 name is not UTF-16
   aligned", which the conversion removes.
7. `ps3_roster_probe.compare_rosters(converted, Roster.ROS)`: `existing_parsers_accept_both = True`,
   `root_counts_equal = True`, `root_pointer_differences = []`, nickname odd targets 1,344 -> 0.
8. Idempotence: an Xbox-layout input (converted output, either fixture, any STFS container) is refused with
   "already uses the Xbox 360 layout"; ambiguous palettes are refused rather than guessed; the output is
   deterministic (sha256 `df2658dea378bbd216e8ac452fd9d6cc9af1ebc6518177182b527f3653e4d034`, pinned in
   the retail test).
9. A converted player edit round-trips through `save_roster_players.make_patch`/`verify_patch`.

Resulting content: 40 teams decode (Oilers, 49ers, Browns, Bills, Cardinals, Eagles, Chargers, Seahawks,
Giants, Bears, Dolphins, Colts, Broncos, Falcons, Raiders, Cowboys, Redskins, Buccaneers, Packers, Jets,
Chiefs, Bengals, Saints, Vikings, eight `****` placeholders, Lions, Steelers, Patriots, Rams, Americans,
Bucs, Beasts, Cobras); 11 nicknames survive; 2,254 players keep names, positions and team slots.

## Packaging for Xenia: what the Saves workspace actually does

`save_roster_players.py`, `save_playbooks.py` and `save_appearance.py` all write a **raw** `Roster.ROS`
next to the source with a JSON receipt (`_reserve` with `O_EXCL`, private mode, fsync, reparse) and
explicitly refuse to write STFS containers (no keyvault). There is no content-root or STFS step to reuse,
so the importer writes the same raw payload plus `<name>.ps3-import.json` and states the placement:
Xenia keeps game-created saves as folders under its content root
(`content/54540807/00000001/<save>/Roster.ROS`, the layout `launcher.py` already uses for the title
update), so the raw file replaces the `Roster.ROS` of a save the game created. UNWITNESSED.

## Test output

```
$ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_ps3_roster_convert.py -v
test_zip_member_detection_write_receipt_and_no_overwrite (__main__.FileTests...) ... ok
test_member_selection_and_pointer_rule_counts (__main__.RetailMemberTests...) ... ok
test_runtime_words_match_the_xbox_fixture (__main__.RetailMemberTests...) ... ok
test_strict_readers_names_and_idempotence (__main__.RetailMemberTests...) ... ok
test_idempotence_and_refusals (__main__.SyntheticConversionTests...) ... ok
test_output_is_the_exact_xbox_layout (__main__.SyntheticConversionTests...) ... ok
test_platform_detection (__main__.SyntheticConversionTests...) ... ok
test_receipt_counts_and_claims (__main__.SyntheticConversionTests...) ... ok
test_relocation_when_the_guard_byte_is_owned (__main__.SyntheticConversionTests...) ... ok
test_round_trip_edit_through_the_roster_writer (__main__.SyntheticConversionTests...) ... ok
test_strict_readers_accept_output_and_refuse_input (__main__.SyntheticConversionTests...) ... ok
Ran 11 tests in 8.428s
OK

$ PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_ps3_roster_import_qt.py -v
test_load_ps3_file_enables_import_and_converts_with_receipt (__main__.PanelTests...) ... ok
test_xbox_layout_file_is_refused_without_writing (__main__.PanelTests...) ... ok
Ran 2 tests in 0.804s
OK

Neighbouring suites, unchanged and green: test_apf_save_roster_players.py (7), test_apf_ps3_probes.py (9),
tests/test_apf_save_custom_team_appearance.py (12), test_apf_ps3_texture_bundle_qt.py (3).
```

Real member via the CLI: `APF_PS3_ROSTER_CONVERT_PASS players=2254 teams=40 odd_runs=5 repointed=4991
colours=2660 changed_bytes=24527`.

## UNWITNESSED: what Noah / Aszemple must check in Xenia

1. Copy the converted `Roster.ROS` over the `Roster.ROS` of a save the game created (content root
   `content/54540807/00000001/<save>/`), start APF 2K8 with the studio launcher, load that roster.
2. Rosters: 28 real 1993 teams plus the four leftover APF teams in slots 36-39; names spelled correctly;
   positions and depth charts; the 11 nicknames (Rocket x2, Pepper, Chuckie, A.J., Wes, Tootie, Pat, Mel,
   Flipper, Ickey).
3. Team colours (the palette rotation) on uniforms and menus; if colours look swapped, the rotation
   direction is the first suspect.
4. If the roster refuses to load: the four root runtime words, the 0x230224 block and the bank header words
   are the next suspects, then the team categories 2/0 the roster author chose.
5. Create Player: 475 stale name-pool entries are now blank (they read fragments on PS3); restoring them from
   a stock Xbox roster is the listed follow-up.

## Not done / limitations (honest)

* Stale references that happen to land on a clean string start cannot be detected without the stock file;
  they keep whatever text they read. Only structurally provable damage was repaired.
* No STFS container is written (the studio has no keyvault and Xenia loads folder saves).
* `custom_team_appearance.parse_save` stays informational for this roster (content categories).
* Protected-file hookups (gui.py tab, allowlist, runtime closure, registry row) are described in
  `WIRING.md`, not applied.

ASTRA_DONE
