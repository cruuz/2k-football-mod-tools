# Depth roles (playbooks and depth-chart rows)

This optional ADVANCED playbook pass assigns X/Z/SLOT receiver ordinals and
nickel/dime corner ordinals. It edits existing personnel groups in every PLAY
book, including utility books. The Tier 1 pass has no executable patch;
the separate experimental Tier 2 patch below adds depth-chart rows.
In-game player selection remains unwitnessed.

## Rule and exceptions

The personnel byte is `kind | (ordinal << 5)`: WR kind 9, CB kind 18.
For each shared offensive group with 3–5 receivers, average each slot's
`abs(x[0])` across **all** formations using that group. The smallest mean is
SLOT (ordinal 2). Of the remaining slots, the widest with negative mean x is
X (0), and the widest with positive mean x is Z (1). Remaining receivers get
3, then 4, in descending mean width. Equal widths use ascending slot index.
This is a group-wide convention; it does not guarantee X/Z stay on those
sides in every mirrored or asymmetric formation.

Three-corner groups receive 0/1/2, with the innermost on 2. Four-corner groups
receive 0/1/2/3, with the innermost on 3 and the other inside corner on 2.
The same deterministic width/side rule assigns the outside corners.

A group is **refused as a whole** if its proposed inside slot is more than
2 yards wider than any formation's actual innermost slot. There is no
per-formation override: the group is shared. Its ordinary formations are
excluded too. No groups or formations are split or allocated. Unused groups,
non-offensive WR groups, groups with more than five WRs, and groups without
distinct outside-left/right candidates are preserved and reported.

An offensive formation is `bunch_or_tied` when its two smallest receiver
widths differ by at most 2 yards. This geometric ambiguity includes symmetric
Quads/Empty alignments on opposite sides, regardless of formation name.
Accepted groups containing such formations are still normalised, but those
formations do not get a claim about a unique innermost SLOT. The audit lists
every formation, its category, inner slot/ordinal, x coordinates, ambiguity
and exclusion reason. It also lists disagreement within the tolerance.

The output gate checks all nonexcluded formations for the designated
innermost ordinal and a complete, unique ordinal set. Corners are checked
even when widths tie; the lower slot index breaks the tie. Exclusions are
counted explicitly, never silently treated as successes.

## Measured retail scope

The 37 books contain 1,533 formations, 9,251 plays and 91,833 nodes. The original
466-formation WR histogram includes **35 onside-kick-return formations**;
only 431 are offensive. The all-formation histogram is retained for comparison
with the research: ordinals 0/1/2/3/4 occur 196/115/100/20/35 times.

On retail, 12 shared offensive groups disagree beyond the threshold, affecting
53 formations. Another 85 offensive formations are geometrically ambiguous.
The gate therefore checks **293 offensive formations + 71 nickel + 38 dime =
402**; it excludes **53 + 85 + 35 = 173** formations. Twenty-one unused groups
are also preserved. The 12 disagreements are BAL 5, CHI 4, DEN 4, GB 8, IND 7,
KC 4, NYJ 3/6/7, PIT 8, reference 10 and STL 6 (zero-based group indices).

After the pass, the full WR histogram is 33/12/378/33/10. Every checked
offensive formation has innermost ordinal 2; all 71 nickel and all 38 dime
formations have innermost 2 and 3 respectively. Retail dime's **ordinal set**
was correct in 38/38 formations, but its innermost ordinal was 3 in only 36/38.
The two other formations are corrected, including deterministic tie handling.

## API and CLI

```python
from mod_editor.core import nfl2k5_depth_roles as roles

report = roles.audit(image_or_extracted_pack_folder)
states = roles.status(image_or_extracted_pack_folder)
compiled = roles.normalise(wrapped_play_bytes)  # pure; also accepts authored books
new_bytes, receipt = compiled.replacement, compiled.report
receipt = roles.apply(disc_copy_path)  # in-place, preflight + read-back + rollback
```

`audit` and `status` also accept one wrapped `.PLAY` file, a directory of
wrapped `.PLAY` files, raw resource bytes, or a mapping of keys to resources.
An extracted archive is a `vc_53450030` folder or its parent, not one isolated
numbered pack file. A `.2k5book` JSON recipe must first be compiled by the
existing pack installer. Bare PLAY bodies are not accepted.

`book_status(raw)` returns `retail`, `applied` or `foreign`. The embedded SHA-256
pins cover relevant category indices, role slot indices/ordinals, formation
membership and x[0]. They do not claim whole-book identity. Names, plays,
routes and front-seven position codes are outside this patch's pins; they
still undergo structural/play validation before writing. The front-seven
recode and depth-role byte transformations commute on every retail book.
Run the stock recode API **first**: its own defensive-table pins include CB
bytes and do not recognise an already-normalised role table.

An authored geometry or unknown role footprint is `foreign`, even if already
normalised. `apply(..., allow_custom=True)` explicitly permits that footprint,
but still applies all validation, ownership and exclusion gates. It is
idempotent for custom books as well. Its receipt's `status: applied` means
the operation completed; per-book `after_status` retains the actual pin state.
A mixed archive has aggregate `foreign` status, with individual states listed.

```bash
python3 tools/nfl2k5_depth_roles.py audit /path/to/extracted/game --json audit.json
python3 tools/nfl2k5_depth_roles.py status /path/to/disc-copy.xiso.iso
python3 tools/nfl2k5_depth_roles.py normalise retail.xiso.iso -o roles.xiso.iso --json receipt.json
python3 tools/nfl2k5_depth_roles.py apply roles.xiso.iso --json repeated.json
python3 tools/nfl2k5_depth_roles.py normalise authored.PLAY -o roles.PLAY --allow-custom
python3 tools/nfl2k5_depth_roles.py normalise /path/to/extracted/game -o exported-books
```

Outputs/JSON reports must be new paths. Folder normalisation exports wrapped
books; it does not repack the loose source. Exported resources and detailed
reports are private game-derived artifacts and must not be distributed.
Audit exits 0 on a readable book even when its gate is red (expected for
retail); status exits 1 on `foreign`; normalise/apply exit 1 on a failed check.
`--json -` emits only JSON to stdout.

Every book is compiled before any archive write. The writer changes only the
eleven-byte personnel span of changed categories, verifies the full resource,
and attempts rollback of all touched spans on failure. Rollback failure is
reported explicitly. A process crash/power loss is not transactionally
recoverable; work on an output copy.

## Evidence and witness

Only the high ordinal bits at PLAY body `0x993C + group*0x10 + 5 + slot` may
change. Wrapper, names, all formation geometry/mirror maps, auxiliary masks,
links, plays, nodes and counts remain byte-identical. The writer additionally
sets the required `0x8000 | (group << 9) | play` marker on newly authored links;
the normaliser itself never changes links. Every play passes the existing
ported retail validator before and after compilation.

The optional private-data test executes the actual retail `0xE7530` resolver
for WR/CB ordinals 0–7, bounded to 32 instructions per invocation, with
read-only code/table memory. It proves the `0x4F5930` chain table resolves
even/odd ordinals to rank/side chains and `ordinal >> 1` rows. It does **not**
execute the lineup builder, deduplication, substitutions or fallback ladder.
Ordinal 2 starts at rank row 1, ordinal 3 at side row 1; actual roster identity
must be witnessed. The UI may display those as its second list entries.

Noah should use distinctive receivers/corners in those rows, call ordinary
Trips/Doubles/Spread/Trey plus Nickel/Dime, check a refused group and a
Quads/Bunch set, check substitutions and flipped formations, and simulate a
franchise week to inspect auto-depth reordering. Ensure all huddles break.
No xemu, GUI or audio is invoked by this module or its tests.

## Tier 2: depth-chart rows (EXPERIMENTAL)

`mod_editor/core/nfl2k5_depth_chart_rows.py` adds these views of the existing
position lists. It changes no roster position codes and allocates no lists.

| Unit | Visible rows | Added labels | Position / encoded chain |
|---|---:|---|---|
| Offense | 12 | X and Z replace LWR/RWR; SLOT appended | SLOT: `(3, 2)` |
| 4-3 defense | 13 | NCB / NICKEL CORNER; DCB / DIME CORNER | `(4, 2)`; `(4, 3)` |
| 3-4 defense | 13 | NCB / NICKEL CORNER; DCB / DIME CORNER | `(4, 2)`; `(4, 3)` |
| Special teams | 4 | KR, PR, K, P retained | Original fields |

The 44 × 0x48 table at `0x5140D8` uses storage stride 13. Existing slots keep
their indices within each unit; specials move to absolute records 39–42.
Offense record 12 and final record 43 are all-zero padding. The row-count
callback at `0x243AA0` returns **12/13/13/4**, so offense padding cannot become
a selectable row. This does not depend on the blank guard at `0x242C10`;
that guard also returns zero when directly tested. The six **dwords** of the
KR/PR position list at `0x514D38` are pinned and untouched.

```python
from mod_editor.core import nfl2k5_depth_chart_rows as rows

rows.status(xbe_bytes)                 # retail | applied | foreign
patched_xbe, receipt = rows.apply(xbe_bytes)
assert rows.apply(patched_xbe)[0] == patched_xbe
```

`apply` requires `nfl2k5_position_pools.status(xbe_bytes) == "applied"`, with
the normal third-starter and penalty options enabled. Pools itself requires
modern scheme labels first. EDGE may run before or after these patches; its
writer preserves the scheme-owned 3-4 DE names. Both label writers and the
pool module detect stride 11 or 13. Their existing direct repeated-apply
refusal behavior remains; the orchestrator skips their applied states.
Rows itself returns unchanged bytes and `already_applied: true` on repeat.

SLOT/NCB read **rank row 1**; DCB reads **side row 1**, using the existing
`0x242B07` hook and `0x2BA840` pools cave. These are starting rows for the
on-field resolver, not a guarantee of the third/fourth roster identity:
the builder's deduplication and fallback behavior remain unwitnessed.
The detail lists have `max(0, position_count - 1)` entries after the retail
screen-entry compactor (`0x243790`) makes the rank/side indices dense.
Changing either list changes a shared rank/side field, so another row may
also change. These are role views, not independent saved depth charts.

Two additional correctness fixes accompany expansion. `0x242CA3` now tests
chain bit 0 for swaps: treating chain 2 as merely nonzero would incorrectly
swap the side list. The existing bench block `0x244405..0x244477` computes
the actual row before the `>7` promotion decision and uses the same chain
bit after confirmation. It preserves the displayed row for ordinary
selection, the dialog's stack argument, and the retail list compactor.
There is no additional cave or writable global. The eleven original stride
sites are covered by nine three-byte instruction pins and two whole-block
pins: pools' tab initializer and this bench block own the other two.

The duplicate-starter check (`0x243B50`) deliberately still examines the
original eleven slots. Its four count calls become `mov eax,11`; otherwise
an added role view that aliases a base-row starter could open a warning
every time the chart renders. An actual duplicate among the original
starters still takes the retail warning path.

The full table is checked against a retail SHA-256 after reversing only
recognised pool and label edits. Unknown padding, fields, instruction bytes,
missing dependencies, and partial expansion are refused. Touched `.text`
and `.rdata` digests are updated. This pure module performs no file writes;
the existing build writer owns output copies and Windows binary I/O.

Integration is specified in `WIRING_TIER2.md`; protected build/GUI files are
not changed by this delivery. Select EXPERIMENTAL only until Noah witnesses
the screen. Pair the rows with the Tier 1 playbook pass and the complete
pools build (XBE, books, rosters). The tests execute retail getters, counts,
swaps, duplicate checks, and the bench arm with read-only code pages and
instruction limits. Dialog and bench-compaction call boundaries are stubbed
in the isolated bench test; real screen-entry compaction runs separately.
They do not launch a game or demonstrate clipping, controller interaction,
franchise-week behavior, or on-field player identity. The in-game checklist
is included in `WIRING_TIER2.md` and the delivery report.
