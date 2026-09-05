# SPECIAL tab r61b, 2026-09-05

**EXPERIMENTAL/UNWITNESSED.** The bounded native draw now emits all thirteen
SPECIAL rows and all three player-name columns. Noah's exact labels and order
are implemented. The layout fix changes two existing data fields: row spacing
4 to 1 and label width 50 to 57. Font size, player-column widths, player
resolvers and role chains retain their existing behavior.

Noah's supplied [screenshot](.scratch/special_tab_noah.png) was inspected. It
WITNESSES the previous expanded SPECIAL tab loading in xemu, including the
grown final `.XTLID`. It also shows eleven rows, both scrollbars, and third
jersey numbers without names. It does not witness this revision. No emulator,
GUI display, audio, network, or retail-file write was used during this task.

## PROVED: the third names were suppressed by the sheet's column boundary

The table remains 46 records at `0xEE3000`, each 72 bytes. Every reader keeps
`unit * 11 + slot`. The first three units contain eleven records each; SPECIAL
extends the final unit from four to thirteen. Neither a stride-13 conversion
nor a new storage allocation is part of this correction.

The summary has seven cells per row: abbreviation, first jersey/name, second
jersey/name, third jersey/name. Descriptor addresses in that order are
`0x532280`, `0x532330`, `0x532540`, `0x5323E0`, `0x5325F0`, `0x532490`,
`0x5326A0`. All are frozen columns. The name callback is `0x243AC0`, the
jersey callback is `0x243B00`, and the abbreviation callback is `0x243AE0`.
The player-cell callback cookie `0x20034` passes column and row.

The resolver at `0x242C00` already accepts cells 1 through 6, pairing cells
5 and 6 with the third player. It follows `0x242AE0` and the existing
position-pool getter/chain shift; the name callback reaches the real
`0x145B60` formatter. These routines resolve matching identities and names.
They did not need another third-entry code patch.

The retail widths are `50 + 28 + 145 + 28 + 145 + 28 + 145 = 569` pixels.
Name widths are explicit descriptor floats; jersey widths are two retail
font3 digits at 11 pixels each plus the normal six-pixel padding. When thirteen
rows use the retail 28-pixel pitch, the vertical scrollbar narrows the inner
frame to 567 pixels. The final whole column misses by two pixels. The sheet
then also requests a horizontal scrollbar, further reducing visible height.
`0x171B80` checks complete-column bounds before invoking the row draw path,
so the third-name callback is never called. The adjacent jersey column fits.
This explains the six number-only examples in Noah's screenshot.

The native two-pass layout at `0x172120` uses `0x172040`/`0x171910` to count
rows, `0x172070` to count columns, and `0x16F460` to update scrolling. The
regression reproduces the old 11-row/6-column state and the new 13-row/7-column
state using these actual instructions, without layout hooks.

## PROVED: the smallest integral row-spacing change fits all thirteen

Retail archive outer 3, chunk 73 is the `dc_overview` LAYT. Its
`dc_overviewsheet` node at decoded offset 384 selects style 17, with x/y
15/80, width/height 600/360. All four tab callbacks at `0x243C30`, `0x243C60`,
`0x243C90`, `0x243CC0` select the same screen, `0x533088`. Parsing all 86
retail LAYTs finds no other style-17 sheet. There is no per-unit layout
selector in these descriptors, so the change applies to all four summary tabs.

Style 17 is the existing 48-byte descriptor at `0xAA3744` in file-backed
`.data`, section 13. Its cell height at +0x18 is 24, header height at +0x1C
is 30, font slot at +0x20 is 2 (font3), and row spacing at +0x28 is float 4.
`0x16FAD0` computes height plus spacing. The data edit at `0xAA376C` changes
float 4 (`00 00 80 40`) to float 1 (`00 00 80 3F`), making pitch 25.
The entire 48-byte descriptor is pinned; its other fields are unchanged.

Native probes of gaps 4, 3, 2, and 1 establish that 1 is the largest integral
gap that fits thirteen rows. Whole-pixel spacing avoids fractional placement.
At the resulting inner top/bottom 110/436, the thirteenth row ends at 434,
passing the retail strict bottom-boundary test. Both scrollbars disappear.
Selecting the last row leaves scroll row zero. The other three units retain
eleven rows and all three complete player columns.

The exact requested four-letter labels need a second small descriptor edit:
retail font3 measures SLWR and PWRB at 51 pixels, exceeding the old 50-pixel
label column. At `0x5322D0`, in `.rdata` section 12, width 50
(`00 00 48 42`) becomes 57 (`00 00 64 42`), allowing the normal six-pixel
padding. All player columns retain their retail widths. The final total is
576 pixels within the available 584. The preview was inspected again after
this correction; the labels and jersey numbers have clear separation.

Both edits are descriptor data, not instructions, caves, or runtime globals.
Retail `.data` and `.rdata` have flags 7, including execute permission; this
report does not infer data use from a nonexistent non-executable flag. Section
placement, descriptor references, field interpretation and bounded consumers
establish their data use. No layout code edit is needed.

## Labels, chains and build compatibility

The four retail roles KR, PR, K, P remain first, followed by:

| Slot | Label | Long name | Position | Encoded chain |
| --- | --- | --- | --- | --- |
| 4 | LS | LONG SNAPPER | 12 | 2 |
| 5 | LGUN | LEFT GUNNER | 3 | 3 |
| 6 | RGUN | RIGHT GUNNER | 4 | 3 |
| 7 | NCB | NICKEL CORNER | 4 | 2 |
| 8 | DCB | DIME CORNER | 4 | 3 |
| 9 | SLWR | SLOT RECEIVER | 3 | 2 |
| 10 | GAD | GADGET | 3 | 4 |
| 11 | 3DRB | THIRD DOWN BACK | 7 | 2 |
| 12 | PWRB | POWER BACK | 7 | 4 |

All long names are at most 26 characters. Every role retains its prior
position/chain pair despite relocation and renaming. The low chain bit selects
rank versus side; the shifted bits select the starting list row. RGUN and DCB
intentionally remain aliases of the same CB side-chain view. No independent
role assignment storage is implied. Existing X/Z offense labels are retained.

The depth-roles book algorithm needs no change. The new contract test checks
these labels against the existing PLAY kind/ordinal pairs, and the existing
native picker tests execute the on-field chain readers. The full depth-roles
and special-role suites pass, including fixed-span book normalization and
idempotence checks. Compatibility keys such as `3db` and `pwr` stay unchanged.

The first composed gate run exposed a pre-existing depth-lock bug: it used
stride 13 to recognize expanded rows, although SPECIAL correctly keeps stride
11. `nfl2k5_depth_locks.py` now recognizes expansion by the relocated table
address, selects the corresponding pinned bench/swap profile, and still
rejects stride 13. This unprotected compatibility fix is necessary for the
requested composed gates. Tests verify both application orders, identical
final bytes, replay idempotence, and rejection of a mismatched bench/table.
No depth-lock machine-code body changed in this task.

`nfl2k5_modern_positions.read_depth_chart_units` exposes all four tabs in
on-screen order, including SPECIAL's new abbreviations and long names. Its
older `read_units` API remains defensive-only for compatibility. The GUI
panels are outside the allowed editing scope; exact replacement text and this
preview API are handed off in [WIRING.md](WIRING.md). Existing dispatcher,
build flags and grown-XBE writers already call the changed module. Protected
UI text and cave-manifest regeneration remain Claude's integration work.

Apply pins the complete column/sheet descriptor blocks, including the column
list terminator, as well as all 48 style bytes and both accepted width values.
It refuses old expanded builds, partial layout changes and foreign bytes
before mutation. Rebuild from a recognized retail/dependency source instead
of layering over the former SPECIAL patch. Applying this revision twice is
byte-identical. Existing section helpers repin sections 0, 12, 13, 14 and 21;
the receipt declares the entire style span and width span. `.XTLID` growth
remains the existing 73,728 bytes. No protected manifest was regenerated.

## Before and after previews

- [Before PNG](.scratch/special_tab_before.png): prior role order and style,
  last row selected, scroll row 2. It reproduces K through PWR, both scrollbars,
  and the same SF numbers/names as Noah's screenshot.
- [After PNG](.scratch/special_tab_after.png): KR through PWRB visible together,
  scroll row 0, no scrollbars, all three available names, unchanged retail font.
- [Machine-readable evidence](.scratch/special_tab_preview.json): native layout,
  every cell callback string, widths, hashes and the exact apply receipt.

These are data previews, not emulator captures. `tools/nfl2k5_special_tab_preview.py`
reads the retail SF roster's identities, position, rank/side and returner
indices, executes the real depth compactor, and renders the bounded callback
output using the decoded retail font3 atlas. Availability fields use the
normal synthetic fixture. The frame, headings and scrollbar artwork are
illustrations. GPU/font-state setup at `0x172A60` and final glyph submission at
`0x16F680` are intercepted with their proper stack cleanup. Allocator-owned
sheet/cell structures are constructed in the harness. Layout, scrolling,
cell dispatch (`0x173840`/`0x1728A0`), lookup and name formatting execute
natively. Layout is capped at 200,000 instructions; each draw/compaction at
1,000,000. This proves the emitted text and geometry, not Xbox GPU output.

The restored third SF entries are:

| New label | Third jersey | Native formatted name |
| --- | --- | --- |
| SLWR | 84 | C. Wilson |
| NCB | 36 | S. Spencer |
| DCB | 23 | J. Williams |
| GAD | 1 | C. Conway |
| LGUN | 83 | A. Battle |
| RGUN | 23 | J. Williams |

Private inputs and decoded-body SHA-256 values:

```text
default.xbe: 73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9
dc_overview LAYT: 7443c566c77317efa873a7394f5b800a95935f6f7b7d8a69325a86b1a9d8ac2e
font3 FONT: 330765bb8482457120520cdb9d354a91d6e615f2ae75c9fa93b4542a3882282c
ROST body: b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae
before PNG: f9366387bee3776d7c3025be75cc08a8f893015fd653e67efec485c3912096ae
after PNG: a22e07894141d52631604cca6b2938288bd0af371d50cdb2365207b7d7169944
```

The archive is `vc_53450030/0` under the brief's retail extraction. FONT is
outer 3/chunk 2; LAYT is outer 3/chunk 73. Ghidra shards
`006656_007167`, `007168_007679`, `009728_010239`, `010752_011263` were read
only from the main tree's research corpus. Private resources and PNGs stay
under `.scratch/` and are excluded from the commit.

Reproduce the PNGs without launching a display:

```sh
python3 tools/nfl2k5_special_tab_preview.py
```

## Validation

All commands below were run as standalone plain Python scripts and passed
with no skips on this machine: **99 tests total**.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_depth_chart_rows.py` | 33 passed, 45.040 s |
| `python3 tests/mod_editor/test_nfl2k5_depth_roles.py` | 22 passed, 38.820 s |
| `python3 tests/mod_editor/test_nfl2k5_special_roles.py` | 8 passed, 34.479 s |
| `python3 tests/mod_editor/test_nfl2k5_depth_locks.py` | 17 passed, 24.764 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 9 passed, 9.690 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 10 passed, 18.485 s |

The requested `tests/mod_editor/test_nfl2k5_depth_chart_rows.py` did not exist
at this branch base. It now runs the historical table/storage/selection suite
and adds portable corruption/order tests, private LAYT/FONT checks and native
draw regressions. Short pools of zero through three players preserve paired
blank jerseys/names. All four units and last-row selection are covered.

Both gates compose the existing XBE patch stack, pools, SPECIAL, practice
squad, depth locks and practice reserves, and explicitly account for the
new descriptor ownership. Depth-lock and special-role test files previously
lacked `unittest.main()`; they now actually execute under the mandated
standalone command. Private evidence/Unicorn/Capstone checks retain explicit
skip reasons when unavailable. `git diff --check` passes. The preview command
also succeeds, and both final PNGs were visually inspected.

## HYPOTHESIS and remaining witness work

The bounded result strongly predicts the corrected in-game screen, but
runtime layout loading, GPU clipping, controller interaction and save reload
remain UNWITNESSED. Custom LAYTs that reuse style 17 or replace the measured
frame, and custom fonts with different metrics, are outside the retail proof.
Long player names retain retail fixed-width rendering behavior. The preview
does not model injuries or a full franchise's eligibility state.

Noah's precise witness list, using a disposable output and save:

1. Boot this revision with its required pools and book-role passes. Open all
   four depth-chart tabs. Confirm SPECIAL's exact order is KR, PR, K, P, LS,
   LGUN, RGUN, NCB, DCB, SLWR, GAD, 3DRB, PWRB. Confirm offense and both
   defenses still have eleven rows and ordinary third names.
2. On SF, compare all six third-entry identities in the table above against
   the current roster. Confirm numbers and names are paired. Repeat with a
   second team and longer names. Confirm four-letter labels do not touch the
   jersey numbers and the unchanged font remains readable on every tab.
3. Select PWRB, move to KR and back, and switch away/back. All thirteen rows
   should remain visible with no vertical/horizontal scrollbar or automatic
   scroll. Check focus highlight, header and bottom border clipping.
4. Use a team with short WR/CB/HB lists. Missing entries should show paired
   blanks, not stale names. Swap SLWR, NCB, LGUN and RGUN entries and confirm
   the intended rank/side lists change. RGUN/DCB should change together.
   Check LS, 3DRB, PWRB, returners and a confirmed bench promotion too.
5. With depth locks enabled, repeat role swaps, advance a week, save, exit
   and reload. Confirm assignments and returners persist as specified in the
   earlier lock handoff. Test injured/absent players separately.
6. Play appropriate offensive, nickel/dime and special-teams snaps and verify
   the book pass still selects the displayed role identities. The new labels
   must not imply independent lists where chains are shared.

This report and WIRING document the choices without requiring questions.
No protected file, release artifact, other worktree or retail asset was edited;
no push was performed. The explicit-path worktree commit failed because Git
could not create its `index.lock` on the read-only filesystem. The brief's
fallback is a commit bundle at [.scratch/r61b-special-tab.bundle](.scratch/r61b-special-tab.bundle),
created through a private Git repository under `.scratch/`, with all edits
left in place. Its parent is branch base
`e6784e70f185567899b4256a4b8ef492dd96c7dd`; the original branch could not be
advanced. The bundle contains only this task's twelve explicit paths, never
`ASTRA_BRIEF.md` or `.scratch/` assets.
