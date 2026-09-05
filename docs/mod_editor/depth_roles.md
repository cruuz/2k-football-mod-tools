# Depth roles (playbooks and depth-chart rows)

This optional ADVANCED playbook pass assigns X/Z/SLOT receiver ordinals,
nickel/dime corners, gunners, a long snapper and bounded offensive role
substitutions. It edits existing personnel groups in every PLAY
book, including utility books. The Tier 1 pass has no executable patch;
the separate experimental Tier 2 patch below adds depth-chart rows.
Noah witnessed the earlier X/Z/SLOT rows working; the new SPECIAL layout and
formation substitutions still require an in-game witness.

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

A group's **WR assignment is refused as a whole** if its proposed inside slot is more than
2 yards wider than any formation's actual innermost slot. There is no
per-formation override: the group is shared. Its ordinary formations are
excluded too. No groups or formations are split or allocated. Unused groups,
non-offensive WR groups, groups with more than five WRs, and groups without
distinct outside-left/right candidates are preserved and reported. Independent
HB assignments may still change the same group's HB slot. A refused GADGET
assignment leaves the original X/Z/SLOT rules responsible for WR ordinals.

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
membership and x[0]. SPECIAL additionally pins its classification geometry,
shotgun bit, semantic heavy-set classification, snap sources and WR handoff
targets. They do not claim whole-book identity. Unrelated names, routes
and front-seven position codes are outside this patch's pins; they
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

Only role personnel at PLAY body `0x993C + group*0x10 + 5 + slot` may change.
Ordinary roles change only ordinal bits. The two punt gunners may also change
kind to WR/CB. Wrapper, names, all formation geometry/mirror maps, auxiliary masks,
links, plays, nodes and counts remain byte-identical. The writer additionally
sets the required `0x8000 | (group << 9) | play` marker on newly authored links;
the normaliser itself never changes links. Every play passes the existing
ported retail validator before and after compilation.

The optional private-data test executes the actual retail `0xE7530` resolver
for WR/CB/C/HB ordinals 0–7, bounded to 32 instructions per invocation, with
read-only code/table memory. It proves the `0x4F5930` chain table resolves
even/odd WR/CB ordinals to rank/side chains and `ordinal >> 1` rows. Single-chain
C/HB use the ordinal directly as their rank row. A further bounded test executes
the native `0xE8790` picker, `0xE7810` list reader, `0xE7580` dedup and `0xE8340`
starter gate against constructed dense lists, with no call stubs. Every SPECIAL
role matches its chart getter; an already-used player makes the picker advance
to the next list entry. It does **not** execute the complete lineup builder,
franchise auto-depth or every substitution/fallback scenario.
Ordinal 2 starts at rank row 1, ordinal 3 at side row 1; actual roster identity
must be witnessed. The UI may display those as its second list entries.

Noah should use distinctive receivers/corners in those rows, call ordinary
Trips/Doubles/Spread/Trey plus Nickel/Dime, check a refused group and a
Quads/Bunch set, check substitutions and flipped formations, and simulate a
franchise week to inspect auto-depth reordering. Ensure all huddles break.
No xemu, GUI or audio is invoked by this module or its tests.

## SPECIAL formation substitutions

`nfl2k5_special_roles.py` plans independent assignments inside the Tier 1
normaliser. Base offensive personnel must have QB in slot 0 and two tackles,
center and two guards in slots 1–5. Classification does not mistake kick
return personnel for offense.

* **3DB:** one HB, plus shotgun flag bit 19 corroborated by QB depth; or at
  least three WRs; or three WR/TE receiving positions with the HB split at
  least five yards wide and no deeper than three yards. Assign HB ordinal 1.
* **PWR:** goal-line/jumbo categories or names, or at least two TEs plus FB
  (the precise I-heavy definition). Assign HB ordinal 2. Ordinary I Pro with
  one TE remains base. Clock inherits its heavy personnel group's PWR choice.
* **Base:** retain/use HB ordinal 0. Empty sets without an HB get no HB edit.
* Refuse multiple HBs, contradictory shotgun geometry/flag, simultaneous
  passing/power classifications, and shared groups whose HB requests differ.
  Groups are never split. The retail MIN two-HB sets are explicitly ambiguous.
* **GADGET:** actual WR-targeted handoff opcode `0x13` plus target take-handoff
  opcode `0x16` identifies a receiver carry. WR rank row 2 (ordinal 4) keeps
  it distinct from SLOT and both HB roles. Agreeing two-WR groups use that
  receiver; three-plus-WR groups retain X/Z/SLOT priority. Disagreeing carrier
  slots and HB direct snaps are refused for this WR-backed role. This is a
  shared-group formation substitution: other formations and normal plays in
  an accepted group also field that gadget receiver, including at an outside
  WR spot. It is not a per-play substitution.
* **GUN/GUNR:** punt type 10 with a punter, two unambiguous outside coverage
  positions at least ten yards wide, within one yard of the line. Left uses
  WR ordinal 3 (side row 1); right uses CB ordinal 3 (side row 1). These are
  explicit positional lists, not an unimplemented fastest-player sort.
* **LS:** punt type 10 and FG/PAT type 12 with their correct specialist;
  all linked snap opcodes must agree on the central C slot within 30 cm of
  `(0,0)`. Assign C ordinal 1. Retail already uses this second center.

The measured retail HB histogram is **0:885, 1:13, 2:4, 3:3** across offensive
formation slots. MIN supplies eleven ordinal-1 second HBs; PRACTICE supplies
nine other backup ordinals. Every other book's offensive HB is ordinal 0.
There are 36 punt and 36 FG/PAT formations, not 37 each: PRACTICE has neither.
Editor personnel differs from the other 35 books. Ordinary retail punt left
coverage is CB ordinal 2, right is FS ordinal 1; Editor uses WR ordinals 4/3.
Both versions' snapper is C ordinal 1, as are all FG/PAT snappers.

The audit identifies **242 WR-carry formations / 357 distinct linked plays**;
56 WR-carry formations accept GADGET, affecting **265 formations total** in
their shared personnel groups, including ordinary plays. It also finds 22 offensive formations
with an HB direct-snap play; those are reported, not presented as absent
Wildcat-style football. The WR-backed GADGET pass leaves those HB slots to
the independently classified HB role. Accepted counts are **356 3DB,
159 PWR, 36 punt gunner pairs and 72 LS views**. Refused assignments remain
visible in receipts and [the per-book audit](special_roles_audit.json), which
also lists all affected shared-group formations. Prior Tier-1-only books
with recognised signatures can be upgraded; partial/unknown role edits refuse.

## SPECIAL depth-chart rows (EXPERIMENTAL)

Offense, 4-3 and 3-4 have **11 rows**, with X/Z labels on the original WR rows.
SPECIAL has **13 rows**, scrolling only on SPECIAL:

| Row | Abbreviation / long name | Position, chain | List start | Book kind, ordinal |
|---:|---|---|---|---|
| 0–3 | KR, PR, K, P | Retail | Retail | Retail |
| 4 | SLOT / SLOT RECEIVER | 3, 2 | WR rank 1 | 9, 2 |
| 5 | NCB / NICKEL CORNER | 4, 2 | CB rank 1 | 18, 2 |
| 6 | DCB / DIME CORNER | 4, 3 | CB side 1 | 18, 3 |
| 7 | GDGT / GADGET | 3, 4 | WR rank 2 | 9, 4 |
| 8 | GUN / LEFT GUNNER | 3, 3 | WR side 1 | 9, 3 |
| 9 | GUNR / RIGHT GUNNER | 4, 3 | CB side 1 | 18, 3 |
| 10 | LS / LONG SNAPPER | 12, 2 | C rank 1 | 6, 1 |
| 11 | 3DB / 3RD DOWN BACK | 7, 2 | HB rank 1 | 10, 1 |
| 12 | PWR / POWER BACK | 7, 4 | HB rank 2 | 10, 2 |

All indices remain `unit * 11 + slot`: units 0–2 occupy records 0–32 and
SPECIAL records 33–45. No multiplication uses 13. The count callback at
`0x243AA0` retains retail code except `0x243AB1: 4 → 13`. The two title strings
at `0xE8894C` and `0xEA28D8` become SPECIAL, NUL-padded in their original
UTF-16 fields. Every abbreviation fits four characters and every long name 26.

The 44-record retail allocation at `0x5140D8` is too short. **Storage decision:**
no existing `.rdata` cave was certified, so no unknown cave is overwritten.
`nfl2k5_depth_chart_storage.py` adds a fresh read-only tail beyond the retail
image, retaining the final `.XTLID` section's complete original payload.
The 46 × `0x48` table resides at **`0xEE3000..0xEE3CF0`**. The final section
gets preload (`0x38 → 0x3A`), larger virtual/raw sizes and a new digest;
SizeOfImage grows accordingly. These flags follow the
[primary XBE definitions](https://github.com/Cxbx-Reloaded/Cxbx-Reloaded/blob/master/src/common/xbe/Xbe.h).
The original table and KR/PR list at `0x514D38` are untouched.

This deliberately differs from reusing a region inside retail `.rdata`:
it is a fresh loader allocation. The cave oracle's `unknown` result is **not**
promoted to free. A separate bounded allocation check uses its validated
mapping and ownership manifest, verifies the page is beyond the original
image, and scans every byte alignment of all section/header dwords and
relative transfer encodings for the entire new page. There are no hits or
other owners. Synthesized addresses and external loader effects are outside
that static evidence; boot/loading remains unwitnessed.

All 18 retail table references are covered: base ×2, name ×1, position ×7,
chain ×8. Sixteen whole instructions are patched directly; tab-init and bench
own the other two readers as complete replacement blocks. The tab initializer
also gains its chain read. Modern labels, pools and EDGE resolve the active
base while accepting only retail stride 11. Previous stride-13 builds refuse;
rebuild them from retail. All original eleven multiplication sites are pinned,
including the two replaced blocks. No new code cave or writable flag is used.

Rows require complete position pools, including hook `0x242B07`, cave
`0x2BA840`, and the list initializer. List lengths are
`max(0, position_count - (chain >> 1))`: chain 2/3 subtract one; chain 4
subtracts two. Actual native getters, summary columns, detail navigation,
swap/bench paths and the count callback are bounded-tested for all nine roles.
The table's page is read-only during execution. KR/PR/K/P list lengths and
lookups are compared directly with retail.

Swap `0x242CA3` tests chain bit 0. Bench `0x244405..0x244477` compares the
shifted row against seven, preserves the displayed row and dialog stack,
and promotes in the correct rank/side field. The duplicate-starter routine
and all four calls to its count helper stay byte-identical: unit 3 already
bypasses that ordinary starter warning, and original duplicates still warn.

These are shared list views, not independently saved roles. **GUNR and DCB
are the same CB side-row view.** A view can change another row, and the native
picker advances past a player already used elsewhere. Short rosters invoke
retail fallback; no specific roster identity is guaranteed in every formation.

The XBE grows from 11,948,032 to **12,021,760 bytes (+73,728)**. The tested
`storage.write_image_xbe(fd, payload)` appends a grown file to an output disc
and switches only default.xbe's root-directory sector/length. It verifies and
rolls back on failure; same-size replays reuse the allocation. The protected
builder and extent reader must be wired to this helper before a disc build.
See `WIRING_SPECIAL.md` and `ASTRA_ROWS_SPECIAL_REPORT.md` in the worktree root.
The reservation generator now understands this explicit append and extended
image ownership, but **Claude must regenerate the manifest** after wiring;
its source-fingerprint freshness check intentionally remains enforced.
