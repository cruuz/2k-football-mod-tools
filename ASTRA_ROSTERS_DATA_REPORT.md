# r62 Rosters data report

2026-09-05. Branch `astra/r62-rosters-data`, base
`5f5b5047d42984ee41449c4a03669e0945a22f2a` (`local/stack-beta-62`).
**EXPERIMENTAL / UNWITNESSED.** No game, console emulator, visible GUI, audio,
network or push was used. Qt ran offscreen. Source saves, retail extraction,
XISO, hub research and other worktrees were not modified.

## Delivered and decisions

The existing beta-61 roster codec already named and round-tripped all three
style bytes. Its Style page already contained the controls. This work completes
the requested plain parity presentation and repairs exact undo rather than
adding duplicate controls or changing the compatible storage keys:

- Power Run Style has Finesse / Balanced / Power, writing 1 / 50 / 99, plus the
  existing raw value. Both individual and bulk undo now restore a noncanonical
  source value such as 38 exactly. Previously undo of a bucket edit quantized it
  to 50. Thresholds remain 33 and 66.
- Scramble shows **"odd = scrambler"** plainly on the page, on the parity card
  and in the header. The Even / Odd toggle changes only bit zero; magnitude and
  presets retain parity. A rounded numeric edit also refreshes the spin box so
  the displayed value equals the actual byte. The prior "signature release"
  claim is removed from these controls: the exact motion remains unwitnessed.
- Kicking Style keeps Punter=1, Default=49, Kicker=99 presets and experimental
  wording. No guessed straight-on/soccer-style semantics were introduced.
- `power_run_style`, `kicking_style`, `scramble`, the derived `throw_style`,
  their bit locations and the sparse JSON schema stay compatible. CSV exports
  the three raw bytes; importing 97 keeps odd parity. Whole-number validation
  rejects floating-point, Boolean and string values at named style setters.
  Legacy 0..255 byte round trips and the existing above-99 warnings remain.

`nfl2k5_team_names_2026.py` and `data/nfl2k5_team_names_2026.json` implement the
opt-in data pass, pure resource status/apply, a bounded private-image adapter,
actual-name reader and shared Team Identity catalog preview. Every preset is
specified off. Protected Build and facade wiring is fully spelled out in the
new r62 section of `WIRING.md`; the brief expressly assigns those edits to Claude.
There is no new executable patch or allocation.

`nfl2k5_roster_ages.py` implements read-only preview followed by a stale-preview-
checked in-memory transaction. Tools -> **Shift ages to season year...** provides
source and target seasons (target 2026), optional shown-list scope, change/skip
review and an Apply action. Undo/Redo is shared with the roster/franchise edits.
Tools also shows and exports the receipt. Saving uses the existing explicit
signed-save/disc-copy or CSV/roster-JSON paths. Nothing runs on load or Build.

The pass preserves ages on September 1, for primary NFL-flagged players aged
18..55 in the chosen source season. The broad ceiling is a deliberate eligibility
rule, not a claim about a typical NFL roster. Templates, non-NFL/history records,
unflagged prospects, invalid dates and implausible ages are listed as skipped.
February 29 moves to February 28 in a non-leap target year, with a receipt note.
The receipt includes identity, record offset, dates, before/after field values,
every changed byte offset/value, source/target seasons, hashes and skip reasons.
Repeated same-season-pair shifts are suppressed per player during the session;
undo restores eligibility. Reloaded saves cannot reveal their age provenance,
so the source season remains an explicit choice. A no-op preserves legacy
noncanonical birth encodings too. No hidden metadata bytes are allocated.

Birth years remain the beta-61 modulo-100 encoding in the seven existing bits,
resolved within a chosen 100-year window. The header now reports the selected
context's September 1 age instead of always September 2004. Membership
`adopt_body` now carries `reference_year` and `base_year` into re-decoding, which
previously dropped that context. Validation reports implausible context ages.
No change to calendar fields, years pro, contracts, stats, ownership, ratings or
progression is part of an age shift. These are fictional shifted birth dates,
not a modern real-player database.

## Every team difference and the exact space limits

Four franchise identities changed since 2004. Arizona's ARZ -> ARI is an
additional deliberate abbreviation convention; Arizona did not relocate or
rename. Washington retains WAS. Jacksonville retains JAX. No abbreviation
convention changes are inferred for the other teams.

| Team index | 2004 identity/code | Requested 2026 identity/code | Actual fixed-space output | Character limits causing fallbacks |
|---|---|---|---|---|
| 7 | Arizona Cardinals / ARZ | Arizona Cardinals / ARI | Arizona Cardinals / ARI | 3 for both abbreviations and label code; fits |
| 8 | San Diego Chargers / SD | Los Angeles Chargers / LAC | L.A. Chargers / LA | City 9 (20 bytes); code 2 (6 bytes), both identity codes and label code |
| 22 | Oakland Raiders / OAK | Las Vegas Raiders / LV | L Vegas Raiders / LV | City 7 (16 bytes); code 3 (8 bytes), LV fits |
| 23 | St. Louis Rams / STL | Los Angeles Rams / LAR | L.A. Rams / LAR | City 9 (20 bytes); code 3 (8 bytes), LAR fits |
| 25 | Washington Redskins / WAS | Washington Commanders / WAS | Washington Cmdrs / WAS | Nickname 8 (18 bytes), both identity and label strings; Commanders needs 10 |

All limits are UTF-16 code units excluding the terminator; bytes include it.
These ASCII short forms fit the existing allocations. The writer zero-fills
the remainder, never extends a span, never moves a pointer and never consumes
neighboring padding. Full Los Angeles, Las Vegas, LAC in the Chargers' two-unit
slots, and Commanders are deliberately refused by the fixed-span encoder. The
Build tooltip and Team Identity preview must show the actual short forms, with
full intended names only in the explanatory review. All 32 retail/desired/written
rows, exact offsets, allocations and pointer fields are in the manifest.

The other 27 are unchanged: San Francisco 49ers, Chicago Bears, Cincinnati
Bengals, Buffalo Bills, Denver Broncos, Cleveland Browns, Tampa Bay Buccaneers,
Kansas City Chiefs, Indianapolis Colts, Dallas Cowboys, Miami Dolphins,
Philadelphia Eagles, Atlanta Falcons, New York Giants, Jacksonville Jaguars,
New York Jets, Detroit Lions, Green Bay Packers, Carolina Panthers,
New England Patriots, Baltimore Ravens, New Orleans Saints, Seattle Seahawks,
Pittsburgh Steelers, Houston Texans, Tennessee Titans and Minnesota Vikings.

**PROVED location:** main disc ROST, archive outer 5, pack 0 virtual offset
0x392800, wrapper 0x20 + body 0x90F60. The 52-team table starts at body 0x41C8,
stride 0x1F4. Per-team nickname +0x104, abbreviation +0x108, city +0x138 and
city abbreviation +0x13C are field-relative UTF-16 pointers. Asset code +0x10C
is pinned and untouched. The independent 36-entry nickname/abbreviation table
starts at body 0x29B0, stride 8, with count/pointer at +0x88/+0x8C. It is patched
in the same grouped operation, so the display-label copy cannot stay retail.

**PROVED STRG audit:** the existing bounded resource scanner found two STRG
banks. Outer 23 chunk 65, chunk offset 2,320,144, body 160,432 bytes: 1,106 string
allocations. Outer 4248 chunk 1, offset 108,848, body 6,080 bytes: nine allocations.
The existing strict parser decoded all **1,115** allocations. None contains
Redskins, Oakland, San Diego, St. Louis, Chargers, Raiders or Rams. The franchise
bank uses dynamic team placeholders. **Zero STRG writes.** Historic ROSTs,
stadium names, menu executable literals, asset codes, uniforms/logos, commentary,
trivia and historic achievements are outside this data pass.

## Integrity and measured retail results

The name manifest pins the wrapper, preamble, team/label table identity and 35
string/pointer cells. Every cell must be exactly retail or exactly installed;
the 17 changed cells must agree on the state. Any mixed install refuses before
mutation. Every decoded text-pointer domain is checked for shared and interior
references to owned spans, including player, college, stadium, coach, historical
slug and generated-name tables. Ordinary unrelated edits remain composable.
The image adapter uses existing OuterImage handles, binary mode, moved pack
lookup, read-before-write and exact readback. It writes only a caller's private
build copy and closes on errors. It is not a power-loss-atomic disc transaction.

**PROVED:** 17 name spans, **182 allocated bytes**, **66 bytes actually changed**,
zero growth; all other resource bytes and all pointers remain identical. Pure
replay returns identical bytes and reports zero changed spans. A relocated-pack
synthetic XDVDFS image passes the real image adapter and whole-image comparison.
The largest synthetic image is below 1 MB. No whole retail XISO or pack was
loaded into memory; the only saved retail artifact here is the bounded ROST in
`.scratch/`, excluded from delivery.

**PROVED:** the retail age preview changes **1,944** players, skips **603** other
records, writes **3,888** bytes and preserves every changed player's September 1
age (range 20..49). There are no retail leap-day adjustments in this run; synthetic
February 29 tests cover the fallback. Context-aware CSV import reproduces the
entire changed body exactly. Signed synthetic save-copy readback also matches
exactly and leaves source SAVEGAME.DAT and EXTRA unchanged.

**PROVED:** names compose in both orders with age/style edits and with the actual
position reclassification, team-history pool and prospect-name writers. Tests
compare the complete resulting resources, not only their named fields.

| Payload | SHA-256 |
|---|---|
| Retail complete ROST | `a5cf52fa5d1f2ecf911ef093a1afe6d3e4efbb2ce4d794b876c15a3ad537bacd` |
| Retail ROST body | `b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae` |
| Names-only complete ROST | `8a3adb71c87957b9b551cdbf3eb32dfff527d768b09d4252b29b6b5b6733abd7` |
| Ages-only ROST body | `f193382d9687b5d5aa57008a3acef7bc9806bc11ca5f34c58d3544862e8bb695` |
| Shipped names manifest | `fea1e37b7fb23887b8231d3e971b5113eeecef1d815001b9032da6b0eac8d13b` |

The full-roster offscreen exercise exposed a 37.034-second undo caused by
per-player whole-roster checks. The final bulk transaction computes dirty state
once and refreshes once: measured **0.907 s apply / 0.038 s undo**, restoring the
complete original body. These are local observations, not a portable timing bound.

## Tests actually run

All files below ran as individual plain-Python unittest processes from this
worktree. Qt used `QT_QPA_PLATFORM=offscreen`; no pytest fixtures were needed.
Final results: **310 tests, 308 passed, two precise evidence skips, zero failures**.
The skips are the absent private portrait catalog in the roster codec suite and
the absent private uniform catalog for the Studio-shell mount check. The new
Team Identity catalog test uses the actual retail ROST with a bounded temporary
inventory and does not depend on either absent catalog.

| Command | Final result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_franchise_save.py` | 13 run, PASS |
| `python3 tests/mod_editor/test_nfl2k5_roster_records.py` | 108 run, 1 skipped, PASS |
| `python3 tests/mod_editor/test_nfl2k5_team_names_2026.py` | 9 run, PASS |
| `python3 tests/mod_editor/test_nfl2k5_text_catalog.py` | 9 run, PASS |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_roster_editor_panel_franchise.py` | 2 run, PASS |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_roster_editor_panel_qt.py` | 50 run, 1 skipped, PASS |
| `python3 tests/mod_editor/test_rosters_data.py` | 10 run, PASS |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_rosters_data_qt.py` | 6 run, PASS |
| `python3 tests/mod_editor/test_rosters_reserves_abilities.py` | 13 run, PASS |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_rosters_reserves_abilities_qt.py` | 7 run, PASS |
| `python3 tests/mod_editor/test_rosters_salary_native.py` | 1 run, PASS |
| `python3 tests/mod_editor/test_save_roster_import.py` | 12 run, PASS |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_text_rosters_panel.py` | 14 run, PASS |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_ux_rosters_words_qt.py` | 4 run, PASS |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 28 run, PASS |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 24 run, PASS |

Also ran `python3 -m py_compile` on the new core modules and owned panel, and
`git diff --check`. The read-only retail scan command was:

```sh
python3 tools/nfl_resource_scan.py \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --json .scratch/rosters-data/inventory.json
```

The scan walked 4,323 outer entries / 86,882 bounded resource wrappers. Existing
strict `nfl2k5_text_catalog` functions performed STRG decoding and ROST reference
counts. Both XBE safety gates ran unchanged; no executable owner belongs to this
job. Initial local test failures were corrected: new-test assumptions about
unchanged Scramble, catalog IDs/field names and ValidationError inheritance;
the pre-existing style-caption expectations; and two existing text test files'
missing standalone import paths. Every failed file has a passing final run.
Private logs and full age/name receipts are under `.scratch/rosters-data/`.

## HYPOTHESIS, known limits and Noah's witness list

Only byte behavior and offscreen host UI behavior are proved. The exact
Scramble animation, kicking-style motion, in-game text display widths, loaded-
save precedence and all gameplay outcomes remain **UNWITNESSED**. This did not
build a full modern player database, implement longer name allocations, change
logos/audio/stadiums, advance franchise progression or fix post-2099 game dates.
A 100-year shift can produce identical encoded bytes; no-op operations keep the
existing context. Two-digit storage cannot establish century provenance alone.

The Build checkbox, protected facade preview, capability entries and release
allowlist/runtime imports are integration handoffs, not edits in those protected
files. `WIRING.md` specifies all of them, including the explicit absence of XBE
dispatcher/status entries. A full integrated product/release build was not run.

Noah's pending witness list:

1. On a disposable roster, select Power Run Style Finesse/Balanced/Power and
   confirm the style values survive a save-copy reopen. Compare ball-carrying
   motions on paired snaps. Undo a source value 38 and verify it returns to 38.
2. Use a fixed QB, play, camera and settings; compare Scramble 52 vs 53 and
   96 vs 97 with identical Agility. Observe the actual animation difference.
   Separately compare even-low and even-high sums around Scramble+Agility=150.
   Do not treat a parity label as proof of CPU scrambling tendencies.
3. Compare kicking presets 1/49/99 on the same player in field goals and punts.
   Record motion/no-motion findings without assuming soccer/straight-on labels.
4. After Claude's wiring, build a disposable disc with only 2026 names selected.
   Confirm Team Identity and new-franchise menus show exactly L.A. Chargers/LA,
   L Vegas Raiders/LV, L.A. Rams/LAR, Washington Cmdrs/WAS and Arizona/ARI.
   Check standings, schedule, team selection, scorebug and player/team labels;
   verify team identities, uniforms and logos still select the intended clubs.
5. Reopen an older save and confirm its original names remain. Use a retail
   source with the name option off to confirm the retail names return in a new
   franchise. Reject a partially renamed source instead of repairing it silently.
6. For a new 2026 start with a 2004-age roster, preview 2004 -> 2026, inspect
   every skip, apply and export the receipt. Save a separate copy or roster edit
   document. Pair it with the season_2026 calendar patch and confirm player
   cards show plausible ages, with years pro and contracts retained.
7. Reopen that copy, verify EXTRA/signature and birthday persistence, then test
   one franchise advance, a reserve promotion and a save/reload. Use source=2026
   on an already shifted roster; no second age shift should be proposed. Try a
   February 29 player and confirm the documented February 28 fallback.

No gameplay result is called witnessed until Noah actually plays and records it.

## Delivery

Deliverable files remain in this worktree. `ASTRA_BRIEF.md`, `.scratch/`, private
retail data and test saves are excluded from all commit paths. No push is allowed
or attempted. The final commit/bundle receipt is recorded below after the
explicit-path commit attempt.

The explicit `git add -- <15 deliverable paths>` attempt failed with
`Unable to create .../index.lock: Read-only file system`. The brief's authorized
fallback is used: an isolated Git metadata repository inside
`.scratch/rosters-data/commit-repo` holds the explicit-path commit on
`astra/r62-rosters-data`, based on the original commit above. The incremental
bundle is **`.scratch/rosters-data.bundle`**. Import requires that base commit.
It contains only the 15 deliverables and no scratch/private/brief files; source
files remain in place. Bundle verification and committed-file comparisons are
performed locally. No original Git metadata or other worktree is modified.
