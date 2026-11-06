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
  least five yards wide and no deeper than three yards. Since beta-76.4 these
  sets keep HB ordinal 0, the lead back (shotgun and spread runs need him).
* **PWR:** goal-line/jumbo categories or names, or at least two TEs plus FB
  (the precise I-heavy definition). Assign HB ordinal 1, the first man in the
  independent power order (PWRB). Ordinary I Pro with
  one TE remains base. Clock inherits its heavy personnel group's PWR choice.
* **Base:** retain/use HB ordinal 0. Empty sets without an HB get no HB edit.
* Refuse multiple HBs, contradictory shotgun geometry/flag, simultaneous
  passing/power classifications, and shared groups whose HB requests differ.
  Groups are never split. The retail MIN two-HB sets are explicitly ambiguous.
* **GADGET:** actual WR-targeted handoff opcode `0x13` plus target take-handoff
  opcode `0x16` identifies a receiver carry. Since b780 sub1 (Q61) no group is
  given a gadget ordinal (refused as `gadget_is_a_per_play_substitution`):
  personnel belongs to the whole shared group, so the old WR ordinal 4 also
  put the gadget receiver at WR in 35 base sets of those groups. The gadget
  player now comes in per play (`nfl2k5_lineup_roles` rule 3, below) and every
  group keeps X/Z/SLOT.
* **GUN/GUNR:** punt type 10 with a punter, two unambiguous outside coverage
  positions at least ten yards wide, within one yard of the line. Left uses
  WR ordinal 6 (rank row 3); right uses CB ordinal 6 (rank row 3), the SPECIAL
  LGUN/RGUN rows, which no other club formation asks for (b780 sub1; ordinal
  3 made the left gunner the fourth WR of four- and five-WR sets and the right
  gunner the dime corner). These are explicit positional lists.
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
no group takes a GADGET ordinal any more (b780 sub1; before, 56 WR-carry formations accepted it, affecting 265
formations of their shared groups, including ordinary plays). It also finds 22 offensive formations
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

| Row | Abbreviation / long name | Position, chain | List start | Book kind, ordinal | Where he plays (37 club books, v0.9) |
|---:|---|---|---|---|---|
| 0–3 | KR, PR, K, P | Retail | Retail | Retail | returners (team bytes +0x195/+0x196/+0x199), kicker, punter |
| 4 | LS / LONG SNAPPER | 12, 2 | C rank 1 | 6, 1 | snapper in all 36 punt and 36 FG/PAT formations; C2 |
| 5 | LGUN / LEFT GUNNER | 3, 6 | WR rank 3 | 9, 6 | punt left gunner (36); no other club formation asks for it |
| 6 | RGUN / RIGHT GUNNER | 4, 6 | CB rank 3 | 18, 6 | punt right gunner (36); no other club formation asks for it |
| 7 | NCB / NICKEL CORNER | 4, 2 | CB rank 1 | 18, 2 | CB3 in 114 nickel and dime formations; kickoff units |
| 8 | DCB / DIME CORNER | 4, 3 | CB side 1 | 18, 3 | CB4 in 38 dime formations; kickoff units |
| 9 | SLWR / SLOT RECEIVER | 3, 2 | WR rank 1 | 9, 2 | inside WR in 541 three-WR sets (and in 4/5-WR sets) |
| 10 | GAD / GADGET | 3, 7 | WR side 3 | (rule 3) | the carrier spot of the 111 gadget plays of the v0.9 club books, on that play only; no formation asks for it |
| 11 | 3DRB / THIRD DOWN BACK | 7, 3 | HB side 1 | (rule 1) | the lead back on obvious passing downs; no formation asks for it |
| 12 | PWRB / POWER BACK | 7, 1 | HB side 0 | 10, 1 | the back in 217 goal-line, jumbo and heavy-I sets; 2nd back in two-back sets |

**Revision 3 (b780 sub1, Noah 11/03: "a pick never starts somewhere else"; "If I make someone a third down back,
they shouldn't be in every single play. The starting halfback should have priority.").** Every role row reads its own
order from a place no formation asks for (LGUN/RGUN rank row 3, GAD WR side row 3, 3DRB HB side row 1), so a move
within a row never changes the players ahead of it. Beta-76.4 to the beta-80 RC drew 3DRB as the RB rank list itself
(revision 1: the back put at its top became RB1 in every play). Revision 2 (b780 hunt5) started it at RB rank row 1,
which still reordered the Offense RB row. Revisions 1 and 2 read `previous`. `apply` rewrites only their role
records (one chain byte each) and the section digest, and depth locks and the storage check accept them.
`ThirdDownBackMirrorTests` and `test_b780_hunt5_special_rows.py` run the game's own row lookup and SPECIAL swap path:
a 3DRB or PWRB move never moves the Offense RB order. The 32 preserved retail books (entries 4410..4441, historic
sides) keep retail personnel; SPECIAL roles other than KR/PR/K/P do not apply to them.

## Situational lineup roles (`nfl2k5_lineup_roles`, EXPERIMENTAL)

One late allocator owner, applied with the SPECIAL rows. It hooks two 5-byte calls:
- The lineup builder's call to its picker (`0xE8B20` in `FUN_000E89F0`).
- The picker's list-length call at the top of each fallback tier (`0xE87E9`, outside the span `nfl2k5_sim_cb_tackles`
  pins).

* **Rule 1, 3DRB.** On an obvious passing down (3rd or 4th and 5 or more, 2nd and 10 or more: the down at
  `[[0xE602EC]+4]`, the distance from the game's own `0x207950`), a lead-back slot (RB ordinal 0, not a user
  substitution, the club with the ball) asks for the 3DRB first. He plays if he is not on the field, passes the
  picker's gate and is at least as good a receiver (catch + route running) as the starter, on every club. MyCareer
  marks its club human and rewrites RB side = rank, so its 3DRB row is RB2, and old franchise saves keep their own
  rosters, so the check runs for human clubs too (coordinator 11/04).
* **Rule 2, fullback fallback.** With no fullback, the RB fallback tier of an FB slot on the field reads forward from
  RB2 (from the picker's own bound, never the starter). Retail read it from the end, which put in the deepest back.
  When the formation also asks for the power back (an RB ordinal-1 slot), he keeps his own slot and the next back
  plays fullback. When no back is free, the next tier (a tight end) does. The scheduled simulator's own lineup is
  unchanged, so its calibrated carry shares hold.
* **Rule 3, GAD (OFF in beta-80**, coordinator 11/05: a live-game freeze on FC2's attract demo, a node pointer of 0xFED2 read on the snap path; notes in the b780 scratch notes/sub1_rule3_redo.md; no code of the owner reads the builder's play argument now). As designed: The builder is handed the called play (its second argument: `0x18AD10` → `0x18A5D0` →
  `0xE89F0`). Its slot chains are absolute after loading (the reader at `0x1915B0`). When a WR slot of an offensive
  play takes a handoff in that play (the planner's own `0x13`/`0x16` test), the GAD row (WR ordinal 7) is asked
  first for that slot. He takes it only when he is at least as fast as the slot's own pick, on every club (the
  same reasons as the 3DRB). When he takes the spot, the receiver he replaced can fill a later receiver spot of the same
  set, and the last receiver picked sits.

* **Rule 4, injured players on CPU depth charts** (MC1's finding). The weekly CPU auto-depth `0x2BDCF0` ranks by
  rating and never tests the injury bit (player `+0x20` bit 31). Its three calls (`0x247D5C`, `0x248075`, `0x24853D`)
  now run it, then on every league club it sorts list each position's healthy players ahead of its injured ones in
  the rank chain and, for paired positions, the side chain. The league club test is team kind 0, never a
  shared-player all-star, Pro Bowl or historic side. A user club is touched only with "CPU manages my depth chart".
  An injured player moved down loses his rank and side locks, so a healed starter is seated by rating again and
  depth locks' release rule frees a clearly worse locked backup. A changed paired position keeps its rank starter
  out of side rows 0 and 1. Code: `nfl2k5_lineup_roles_injured.S`.
  On RST2's final roster with modern IR, all 121 injured players have 4 or more weeks out (8 or 17), so they start
  on IR and none is on a chart at the franchise start. Rule 4 covers in-season short injuries and builds without
  modern IR. One native pass there leaves 32 injured rank starters and 18 injured side starters. Rule 4 leaves 1:
  a club whose only fullback is hurt. Every healthy order is kept, and a user club is unchanged unless the CPU manages
  its chart.
* **The season-start pass** (MC1's season-2 finding). Entering the regular season of every later season, charts were
  stale league-wide: 20 empty KR1/KR2/PR slots, 29 empty long snapper slots, 12 ST:LS holes, and holes on the MyCareer
  club. The stage advance's tail `0x27EDF0` calls `0x27EB80` after every earlier pass, and the week sim sorts again
  only after week 1's games. Its next call, `0x2BFDD0` at `0x24868C`, now also runs the pass with rule 4 when the
  advance lands on the regular season (stage `[0xE576A4]` 8). The pass also fills an empty long snapper slot (team
  `+0x198`) with the SPECIAL LS, the second center by rank.
  Proof: the game's own stage advance under Unicorn on MC1's RC career (`save_y1s5.bin`, advanced to stage 8 week 0).
  Native: 53 empty special slots, 31 holes and 12 injured starters. With the owner: 4 empty special slots and 14
  holes, all of them clubs with no kicker or no fullback on the roster, and no injured starter. The MyCareer club has
  no problem left. Season 1 starts at stage 8 with no stage advance, and its charts entering week 1 are identical.

Proof: the game's own builder and picker under Unicorn on the v0.9 executable and roster, all 37 club books.
- 3rd and 8 versus 1st and 10 over 1,211 offensive formations: the 3DRB comes in only as the better receiver, on
  human and CPU clubs alike (see the SUB1 sweep log for the old-save, MyCareer and shipped-default rosters).
- Rule 2 changed the FB slot of 84 formations. In two ATL goal-line sets a TE plays FB, because the only other back
  is the power back, who keeps his slot.
- Rule 3 changed none of the 1,281 non-gadget plays. On the 111 gadget plays the GAD takes the carrier spot only
  when he is at least as fast as the slot's own pick. `mod_build.inspect` reads every other owner the same with
  and without the owner.

**Shipped defaults** (`nfl2k5_third_down_back.default_special_rows`, the last step of the final roster file):
- 3DRB is the club's best receiving back (catch + route running; the starter included, the power back excluded), so
  a backup takes obvious passing downs by default only when he is the better receiver.
- GAD is the club's fastest receiver. Where he is the Z or the side slot receiver (side rows 0 and 1, used by the
  base sets) the default is WR1, the X, who is already on the field on a gadget play, so the slot keeps its own pick.
- The 2026 roster tools had written RB3 and WR4 there.

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
