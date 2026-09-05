# SPECIAL rows and formation roles — 2026-09-05

Implemented the final, thirteen-row ADDENDUM 2 layout. Offense and both defenses
use eleven rows and retail stride 11; only SPECIAL scrolls. All three briefs
were read, including the two SPECIAL addenda. No emulator, GUI or audio ran.
No protected file, release pin, private input or reservation manifest was edited.

**Handoff required before a disc build:** the 46-record table uses fresh
read-only loader storage, so the XBE grows by 73,728 bytes. The protected disc
writer/extent reader, UI wording and release allowlist need the exact changes
in [WIRING_SPECIAL.md](WIRING_SPECIAL.md). Claude must regenerate the reservation
manifest after that wiring. The current builder cannot yet write this larger
XBE. Loading and in-game behavior remain unwitnessed.

## Implemented and proved within the stated bounds

* **Layout:** units 0–2 occupy records 0–32; SPECIAL occupies 33–45. All indices
  remain `unit * 11 + slot`. The eleven original multiplication sites are
  pinned, including two inside complete replacement blocks. The count callback
  at `0x243AA0` changes only its SPECIAL immediate, `0x243AB1: 4 → 13`.
  UTF-16 titles at `0xE8894C` and `0xEA28D8` become SPECIAL. Offense keeps X/Z.
* **Table:** all 18 original references are accounted for: base ×2, name ×1,
  position ×7, chain ×8. Sixteen complete instructions and the tab-init/bench
  blocks use the relocated table. The original 44 records and KR/PR list
  boundary at `0x514D38` remain intact. Modern labels, pools and EDGE resolve
  the active table; all dependency-valid compositions and replay are checked.
  Unknown/partial edits and obsolete stride-13 builds refuse; rebuild from retail.
* **List behavior:** complete pools is required, including hook `0x242B07` and
  helper `0x2BA840..0x2BA860`. Length is `max(0, n - (chain >> 1))`.
  Count, tab initialization, summary columns, detail getters, swaps and bench
  confirmation paths execute bounded native instructions with the table page
  read-only. Counts include 0, 1, 2, 3, 7, 8 and 9 players. Swap `0x242CA3`
  tests the chain's low bit; bench `0x244405..0x244477` uses the shifted row
  for its >7 test and preserves the displayed row and confirmation stack.
  KR/PR/K/P results match retail. All four duplicate-count calls remain exact;
  retail unit-3 bypass and original starter warnings execute correctly.
* **On-field resolver:** actual `0xE7530` maps all role ordinals to the intended
  rank/side list and row. Actual picker `0xE8790`, with `0xE7810`, `0xE7580`
  and `0xE8340`, matches each SPECIAL chart view in constructed dense lists
  and skips an already assigned player. Those functions run without stubs,
  within a 50,000-instruction budget. This does not execute the complete lineup
  builder or prove all saved overrides, fatigue, short-roster or auto-depth cases.
* **Books:** all 37 retail books are recognized; normalization is idempotent
  and composes with position recoding. All 9,251 plays validate; 1,533 formations,
  91,833 nodes, personnel groups, links, geometry and auxiliary masks do not grow
  or change. Only role category-code bytes change; position-kind changes are
  limited to the two punt gunners. Unknown inputs refuse without explicit custom
  policy. Archive preflight/read-back/rollback remains in place.

| SPECIAL row | Position, encoded chain | Formation kind, ordinal | List start |
|---|---|---|---|
| KR / PR / K / P | Retail | Retail | Retail |
| SLOT / SLOT RECEIVER | 3, 2 | WR 9, 2 | WR rank 1 |
| NCB / NICKEL CORNER | 4, 2 | CB 18, 2 | CB rank 1 |
| DCB / DIME CORNER | 4, 3 | CB 18, 3 | CB side 1 |
| GDGT / GADGET | 3, 4 | WR 9, 4 | WR rank 2 |
| GUN / LEFT GUNNER | 3, 3 | WR 9, 3 | WR side 1 |
| GUNR / RIGHT GUNNER | 4, 3 | CB 18, 3 | CB side 1 |
| LS / LONG SNAPPER | 12, 2 | C 6, 1 | C rank 1 |
| 3DB / 3RD DOWN BACK | 7, 2 | HB 10, 1 | HB rank 1 |
| PWR / POWER BACK | 7, 4 | HB 10, 2 | HB rank 2 |

Indices above start at zero. Abbreviations fit four characters; long names fit
26. These are views into existing lists. **GUNR and DCB are the same view.**
Other roles can also affect one another through those lists. Native deduplication
and fallback can select a later player; the labels do not promise independent
saved assignments or a literal overall roster rank in every formation.

## Storage decision and proof boundary

No existing `.rdata` allocation of 3,312 bytes was certified by the cave oracle.
Its unresolved references keep candidates unknown; zero padding alone is not
permission to allocate. The implemented, deliberate departure from a reused
`.rdata` host is a fresh read-only tail on the final `.XTLID` section:

* Table `0xEE3000..0xEE3CF0`, file offset `0xB75C80`.
* Retail image ends at `0xED17C0`; the entire table page is beyond it.
* Preserve and SHA-pin the section's original 5,184 bytes at `0xED0380`.
  Flags `0x38 → 0x3A` add preload without write or execute permissions.
  Grow raw/virtual lengths and SizeOfImage; repin touched sections 0, 14 and 21.
* XBE size `11,948,032 → 12,021,760`. The original table is retained; no runtime
  data lives in `.text`, no new code cave or writable flag is allocated.

The separate allocation check uses the oracle's validated retail mapping and
ownership manifest. It finds zero other owners and zero absolute dword or
relative transfer encodings into `0xEE3000..0xEE4000`, scanning all alignments
in all retail sections and headers as appropriate. It does **not** relabel an
unknown/unmapped cave as free. Synthesized addresses and external loader effects
are outside this evidence. An in-memory recorder test accounts for every appended
byte and loads the extended ownership document; the checked-in manifest was
not regenerated and its freshness guard remains enforced.

`nfl2k5_depth_chart_storage.write_image_xbe()` is ready for the protected wiring.
It appends the whole grown XBE to a disposable disc and switches default.xbe's
directory sector/length after read-back. A synthetic disc proves adjacent files
are preserved, replays reuse the extent, and a short directory write rolls back
the old node and appended bytes. It uses the platform I/O helpers and the caller's
binary descriptor. No full disc or loader boot is claimed from that test.

## Formation policy, retail corrections and counts

**3DB:** exactly one HB and shotgun flag bit 19 agreeing with QB depth, or at
least three WRs, or at least three WR/TE receivers with the HB split at least
five yards wide and no deeper than three yards behind the line. Assign HB 1.
**PWR:** goal-line/jumbo category or formation, or at least two TEs plus a FB.
Assign HB 2. Ordinary one-TE I Pro stays base HB 0; clock sets inherit their
measured heavy personnel. No-HB formations have no back to assign. Conflicting
passing/power evidence, flag/geometry disagreement, multiple HBs and shared
groups whose formations disagree are refused and reported. This is formation
personnel selection, not a runtime down/distance switch.

The retail claim that every HB is ordinal 0 is false: histogram **0:885,
1:13, 2:4, 3:3**. MIN contributes eleven ordinal-1 second HBs; PRACTICE has
nine backup ordinals. All other books' offensive HBs are ordinal 0. The multi-HB
MIN assignments are refused; accepted PRACTICE formations receive their role.

**GADGET:** WR rank row 2 keeps it separate from 3DB/PWR and SLOT. Actual
WR-targeted handoff opcode `0x13` plus take-handoff `0x16` identifies carries;
play-name guesses are not used. There are **242 WR-carry formations and 357
distinct linked plays**. Compatible two-WR groups accept 56 targeted formations,
but their shared groups contain **265 formations total**: the same receiver
also plays ordinary plays. No groups are cloned. At least three WRs conflict
with X/Z/SLOT ownership; disagreeing carriers also refuse. There are 22 offensive
HB direct-snap formations and 35 special-teams direct-snap formations; these
are not advertised as a WR GADGET conversion. Offensive HB direct snaps retain
their independently classified HB role.

**Gunners/LS:** choose one WR side-list reserve on the left and one CB side-list
reserve on the right, providing explicit coverage-player views without claiming
a new speed-sorted pool. Punt outside geometry must agree across the group.
All snap opcodes must agree on the central C slot. There are **36 punt and 36
FG/PAT formations**; PRACTICE has neither, and Editor differs from the other 35
books, correcting the brief's byte-identical-37 assumption. Ordinary retail
punt coverage is CB ordinal 2 left, FS ordinal 1 right; Editor uses WR 4/3.
All punt/FG/PAT snappers already use C ordinal 1. LS exposes this existing choice;
the gunner codes become WR 3 / CB 3 in all 36 punts.

Per-book formation counts below distinguish classification from accepted
assignment. All 159 classified power formations accept PWR; 356 of 387 passing
formations accept 3DB. The other 31 passing formations share conflicting groups.
Full formation names/indices, affected groups and refusal decisions are in
[special_roles_audit.json](docs/mod_editor/special_roles_audit.json); this is
metadata, with no raw book, node or executable asset.

| Book | 3DB classified | 3DB accepted | PWR classified / accepted | GADGET targeted / accepted |
|---|---:|---:|---:|---:|
| ARZ | 9 | 9 | 7 / 7 | 6 / 4 |
| ATL | 8 | 8 | 4 / 4 | 6 / 2 |
| BAL | 8 | 8 | 5 / 5 | 6 / 3 |
| BUF | 10 | 10 | 5 / 5 | 7 / 3 |
| CAR | 12 | 9 | 7 / 7 | 5 / 3 |
| CHI | 10 | 8 | 3 / 3 | 8 / 1 |
| CIN | 13 | 13 | 5 / 5 | 9 / 2 |
| CLE | 13 | 10 | 4 / 4 | 8 / 2 |
| DAL | 10 | 10 | 4 / 4 | 8 / 1 |
| DEN | 7 | 7 | 5 / 5 | 9 / 2 |
| DET | 12 | 11 | 3 / 3 | 7 / 2 |
| Editor | 0 | 0 | 1 / 1 | 0 / 0 |
| GB | 16 | 12 | 3 / 3 | 4 / 1 |
| GEN | 12 | 12 | 3 / 3 | 6 / 1 |
| HOU | 10 | 10 | 4 / 4 | 6 / 1 |
| IND | 13 | 11 | 4 / 4 | 6 / 1 |
| JAX | 9 | 9 | 4 / 4 | 7 / 1 |
| KC | 10 | 8 | 4 / 4 | 7 / 0 |
| MIA | 10 | 9 | 6 / 6 | 8 / 3 |
| MIN | 8 | 8 | 4 / 4 | 7 / 1 |
| NE | 15 | 11 | 4 / 4 | 7 / 1 |
| NO | 14 | 14 | 5 / 5 | 6 / 1 |
| NYG | 9 | 7 | 4 / 4 | 5 / 0 |
| NYJ | 12 | 11 | 5 / 5 | 6 / 1 |
| OAK | 10 | 9 | 3 / 3 | 9 / 2 |
| PHI | 11 | 9 | 6 / 6 | 10 / 3 |
| PIT | 8 | 8 | 5 / 5 | 3 / 1 |
| PRACTICE | 6 | 6 | 3 / 3 | 2 / 0 |
| SD | 12 | 12 | 5 / 5 | 7 / 1 |
| SEA | 13 | 13 | 4 / 4 | 7 / 3 |
| SF | 8 | 8 | 4 / 4 | 5 / 1 |
| STL | 14 | 14 | 4 / 4 | 11 / 2 |
| TB | 14 | 14 | 2 / 2 | 9 / 2 |
| TEN | 9 | 8 | 4 / 4 | 7 / 1 |
| WAS | 10 | 9 | 5 / 5 | 8 / 0 |
| WCO | 11 | 11 | 4 / 4 | 4 / 1 |
| reference | 11 | 10 | 7 / 7 | 6 / 2 |
| **Total** | **387** | **356** | **159 / 159** | **242 / 56** |

Remaining offensive classifications: 337 base, 82 no-HB, 11 ambiguous. Accepted
base assignments cover 237 formations. SPECIAL refusal counts are role/group
decisions, not unique formations: X/Z/SLOT gadget conflict 48, different-list
direct snap 15, shared HB classification disagreement 22, shared gadget carrier
disagreement 24, multiple HBs 2. A refused gadget assignment can still receive
independent HB or core receiver normalization; refusal does not freeze a whole
shared group's bytes.

## Verification

Final combined run: **145 passed, 9 subtests passed, 1 failed** in 202.20 seconds;
no skipped private-data tests. Both required XBE gates pass. The only failure is
`test_retail_current_stack_owns_every_supplied_cave_and_runtime_flag`, reporting
the stale `mod_editor/core/nfl2k5_depth_chart_rows.py` source fingerprint. It
requires Claude's explicitly deferred manifest regeneration. Neither that guard
nor the safety verdicts were relaxed to conceal the pending handoff.

```bash
env -u DISPLAY QT_QPA_PLATFORM=offscreen python3 -m pytest -q \
  tests/nfl2k5_depth_chart_rows_test.py \
  tests/nfl2k5_position_pools_test.py \
  tests/nfl2k5_modern_positions_test.py \
  tests/nfl2k5_edge_rename_test.py \
  tests/mod_editor/test_nfl2k5_depth_roles.py \
  tests/mod_editor/test_nfl2k5_special_roles.py \
  tests/mod_editor/test_xbe_patch_memory_writes.py \
  tests/mod_editor/test_xbe_patch_cave_references.py \
  tests/mod_editor/test_nfl2k5_cave_oracle.py
python3 packaging/repin.py --apply
```

Repin reports **0 pin updates**. The standalone CLI exported all 37 retail books
under `/tmp/astra-special/final-export`: **723 changed bytes**, 179 reported
core/SPECIAL role refusals, combined output gate true. A separate CLI status
read reports all 37 applied; a separate CLI audit confirms the combined gate and
unchanged counts. Report/metadata counts were compared with the final compiler,
and all protected files plus the reservation manifest were compared with HEAD.
No exported game bytes are in the change paths.
`git diff --check` passes.

## Noah's in-game checklist — HYPOTHESES until witnessed

1. Boot a freshly rebuilt retail-derived disc after Claude's wiring and manifest
   regeneration. Confirm the menu loads with the extended preloaded section.
2. Offense, 4-3 and 3-4 each show eleven rows, all three depth columns fit, and
   no vertical scrolling is needed. Offense shows X/Z. SPECIAL's title is correct.
3. SPECIAL contains exactly **KR, PR, K, P, SLOT, NCB, DCB, GDGT, GUN, GUNR,
   LS, 3DB, PWR** in that order. Scroll SPECIAL to the last row; verify labels,
   selection and third depth column at both ends without clipping.
4. Use distinguishable players and adequate WR/CB/HB/C depth. Move each of the
   nine role views, confirm its first/second/third visible entries and intended
   underlying list. Exercise swap and bench confirmation, including cancel and
   shifted rows near the eighth actual list entry. Check DCB/GUNR move together.
5. In accepted formations from the audit, verify X/Z/SLOT receivers, nickel/dime
   corners, 3DB in shotgun/receiving sets, PWR in goal-line/heavy sets, and the
   starter in base sets. Use MIN's multi-HB and a shared-group refusal as controls.
   Do not infer the chosen HB solely from the current down or yards to go.
6. Run an accepted WR sweep/end-around and an ordinary play sharing its group:
   both should use that GDGT receiver. Check a refused ≥3-WR carry and an HB
   direct snap against their documented independent WR/HB assignments.
7. Punt: identify left WR gunner and right CB gunner on both ordinary and Editor
   personnel. Punt, FG and PAT: confirm the selected second-center LS takes the
   snapper slot. Check the snap, block and coverage animations finish normally.
8. Verify KR/PR returns and K/P kicking/punting still work. Reorder a player
   already used elsewhere, test shallow depth/injury fallback, then save/reload
   and franchise auto-depth sorting. Record which list relationships persist.

## Explicit change paths

```text
mod_editor/core/nfl2k5_depth_chart_storage.py
mod_editor/core/nfl2k5_special_roles.py
mod_editor/core/nfl2k5_depth_chart_rows.py
mod_editor/core/nfl2k5_depth_roles.py
mod_editor/core/nfl2k5_modern_positions.py
mod_editor/core/nfl2k5_position_pools.py
mod_editor/core/nfl2k5_edge_rename.py
mod_editor/core/nfl2k5_cave_manifest.py
mod_editor/core/nfl2k5_cave_oracle.py
tools/nfl2k5_depth_roles.py
tests/nfl2k5_depth_chart_rows_test.py
tests/nfl2k5_edge_rename_test.py
tests/mod_editor/test_nfl2k5_depth_roles.py
tests/mod_editor/test_nfl2k5_special_roles.py
tests/mod_editor/test_xbe_patch_memory_writes.py
tests/mod_editor/test_xbe_patch_cave_references.py
tests/mod_editor/test_nfl2k5_cave_oracle.py
docs/mod_editor/depth_roles.md
docs/mod_editor/special_roles_audit.json
docs/NFL2K5_CAVE_ORACLE.md
WIRING_SPECIAL.md
ASTRA_ROWS_SPECIAL_REPORT.md
```
