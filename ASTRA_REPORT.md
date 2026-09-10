# Beta 64: formation changes follow retail personnel

Branch: `astra/b64-formation-personnel`, based on `552ee3c9`.
Scope: one Fine-tune Plays fix, its tests, and the beta-64 changelog entry.
Status: **PROVED offline; UNWITNESSED in Xenia**. No emulator or push.

## Cause verified and change made

The relayed Discord report (2026-09-09) described I Jacks changed to Singleback
Quads retaining 2 RB / 3 TE / 0 WR. The existing `_change_trailer` passed the
record's formation and category into two independent dialog combos. Changing
only the formation therefore preserved the old category. The writer's documented
category getter `0x8485BD38` and eleven-player builder `0x84860020` establish why
the category supplies personnel while the formation supplies alignment. No new
executable research was needed.

- `apf2k8_splb_writer.py` now supplies `retail_formation_packages(index_0a)` and
  `natural_package(formation_index, table)`. Populated SPLB records contribute
  category/count pairs, sorted by descending frequency then ascending category
  index. Unknown formations return `None`. The scan is cached per resolved source
  index path; each caller receives its own dictionary. Sources are read-only.
- Enumeration reuses the existing **`STOCK_BOOKS`** mapping, also used by
  `ApfStudioFacade.play_design_context` and the panel's book picker. No duplicate
  fallback list was introduced. It covers all 15 books, including USER/global.
- The facade exposes the cached table. `_load_book`'s background operation loads
  it and MASTER categories into the panel payload through optional facade readers
  (`getattr`, empty defaults). The dialog reads neither the disc nor the facade.
- Changing the formation selects its natural package and updates a retail hint
  using MASTER names and role counts. Multiple pairings list their record counts.
  Unknown formations retain the package and explain that no pairing is known.
  A never-paired override for a known formation shows a warning, remains selectable,
  and survives acceptance and reopening. Existing record packages are preserved
  when opening the dialog; Add Formation also resolves its initial formation 133.
- The existing trailer compiler/verifier and OR-only normalizer are unchanged.
  No protected file, registry, or build wiring change was needed.

## Retail facts re-derived

Read-only source:
`/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A`.
Retail was present, so all three new retail-gated tests ran.

The scan found **15 books, 209 populated records, 127 formations**: 124 formations
have one package; exactly three have two. Counts are per populated record, not
per play or distinct book.

| Formation | Retail category/count pairs, in selection order |
| --- | --- |
| 72 Tight Triple | 2 Ace ×2; 5 Kings ×1 |
| 78 Pair Slot | 2 Ace ×2; 5 Kings ×1 |
| 120 Gun: Split Spread | 3 Pro Set ×2; 6 Queens ×2 |

| Example | Retail package | Records |
| --- | --- | ---: |
| 9 I Jacks | 0 Jacks | 4 |
| 69 Quads | 8 Flush | 3 |
| 67 Ace Quads | 2 Ace | 1 |
| 126 Gun: Quads Left | 8 Flush | 3 |
| 133 Gun: Straight | 7 Straight | 2 |

`ApfSession.master_categories` re-read all 28 MASTER packages: role IDs 10/11
count as backs, 8 as TE, 9 as WR. Jacks is **2 RB / 3 TE / 0 WR**; Flush is
**1 RB / 0 TE / 4 WR**. The tie for formation 120 resolves to category 3.

## Offline proof and tests

The new standalone unittest file uses entirely synthetic in-memory book fixtures
and the real offscreen `QDialog`, with `exec` patched to drive and accept/cancel
it. It tests frequency ordering, ties, missing formations, source-specific caching,
cache mutation isolation, background payload loading, optional facades, changes,
overrides, warnings, cancellation, and Add Formation's initial default. Its forged
133 pairing deliberately differs from package 7 to catch retaining that constant.

A formation-only I Jacks → Quads dialog action calls
`stage_trailer_replace(0, 69, 8)` and stages **`TrailerReplace(130, 0, 69, 8)`**.
Compilation and independent `verify_book`/`parse_book` prove category 8 in trailer
word A bits 23..17, bit 8 added to word B, and bit 8 added to the `+0x7E04` book
mask. The old Jacks bit remains in both masks; the lower word-A fields and bytes
outside the trailer/book-mask whitelist are preserved. A separate test performs
the same compile/reparse on a real I Jacks record in retail O-ManBlock. Receipts
still report `runtime_lineup_after_replace_proved = False`.

Final commands and unittest output summaries (all exit 0; routine verbose test
names and offscreen Qt `propagateSizeHints`/`setParent` notices omitted):

```text
$ QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_splb_formation_personnel.py -v
Ran 11 tests in 1.026s
OK

$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_splb_add_multiple_formations.py
Ran 14 tests in 0.321s
OK

$ QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_splb_tag_reassignment.py
Ran 86 tests in 2.112s
OK (skipped=1)

$ QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_splb_writer.py
Ran 22 tests in 0.191s
OK

$ git diff --check
(no output)
```

Total: **133 tests, 132 passed, one existing skip**. The skip is the existing
optional decompressed-PE test: its fixture candidates are absent. The new retail
tests skip precisely with `Retail APF 0A absent: <absolute path>` only when that
source is absent.

During test development the first new-suite run had seven setup errors because
the panel loads immediately in its constructor; placing the synthetic reader
patches around construction fixed that test harness issue. The initial
add-multiple command without `PYTHONPATH=.` could not import `mod_editor`; rerunning
with the existing CI root-path setting passed, with that suite unchanged.

## Reporter witness still required

In Playbooks > Fine-tune Plays, select a CPU book's I Jacks record, open
Change formation/package…, and change only the formation to Quads. The package
should move to Flush and the hint should show **1 RB / 0 TE / 4 WR**. Apply and
build the edited copy. When the CPU uses the retargeted record, witness Quads
alignment with **one back, no tight ends, four wide receivers**, replacing the
reported two backs and three tight ends.

That on-field result is **UNWITNESSED in Xenia**. CPU record choice, shared-play
resolution, and residual secondary-mask behavior remain outside this bounded
fix; the report does not claim that every CPU call will use the edited record.
