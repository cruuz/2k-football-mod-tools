# r64 OLB selector removal, 2026-09-07

**EXPERIMENTAL / UNWITNESSED.** Implemented on `astra/r64-olb-row`, based on
`12d2773`. A complete zero-OLB roster scan removes the Outside Linebackers entry
from all sixteen native position selectors serving the fifteen page families.
Every selector retains exactly one Linebackers entry and its Fullbacks entry.
Custom enum-10 players keep their own selectable Outside Linebackers entry.
The gameplay, depth-chart and ratings merge is unchanged.

The protected Build/UI/manifest integration is an explicit handoff in the final
r64 section of `WIRING.md`. The old builder still uses the conservative retained
profile until that handoff is applied. This report does not claim a newly built
disc or a played fix. No network, emulator, GUI display or audio was used.

## PROVED: the original array model needed correction

The brief's addresses such as `0x5545E8` point to a page's **name field**, eight
bytes inside the descriptor. A descriptor starts with callback `0x27CCD0`
(`mov eax,ecx; ret`) and its argument encoding, not a class/vtable pointer.
Its name pointer is at `+8`, position callback binding at `+0x18`, literal enum
at `+0x20`, player count binding at `+0x30`, getter binding at `+0x48`, saved sort
pointer at `+0x94`, and NULL-terminated column pointers at `+0x9C`.

The actual selector is a NULL-terminated **table of four-byte page pointers**
at `sheet + 0xF4`. Physical page spacing ranges from `0xB0` to `0x128`; it is
not the selector stride. Player Trade and Trading Block share their descriptors
but have separate pointer tables, making sixteen selectors for fifteen families.
Pro Bowl already uses this architecture to move K/P pointers to the end.

The selected mechanism is preference (b), applied to the actual list records:
remove one OLB pointer, shift its successors left **four bytes**, and leave two
zero words inside the original complete span. All descriptors, column lists,
callbacks, enum literals and sheet/frame pointers keep their original addresses.
Preference (a) was rejected: the pinned count, selector and renderer path does
not consult a per-page visibility flag. There is no justification for borrowing
visibility bits from unrelated menu structures. Moving entire page descriptors
is unnecessary and would demand changing absolute page/column references.
No screen was guessed from text matching; the lowercase draft spelling is covered.

## PROVED: reader chain and traversal

All sheets use the same native reader chain:

- `0x27CDF0`: descriptor `+0x14` points to a frame list. Walks frames by `0x14`
  to NULL, at most four sheets, passing each sheet to `0x1749D0`.
- `0x1749D0`: constructs a sheet, selects its first page pointer at `sheet+0xF4`,
  then invokes `0x1746C0` and `0x174140`.
- `0x170910`: counts four-byte pointers to NULL. `0x1706C0`: derives the current
  ordinal by walking that same table. Neither count is a position enum.
- `0x174CB0` / `0x174CE0`: next/previous pointer, forward/backward wrap using
  the terminator. `0x174D30`: indexed selection at `sheet+0xF4+4*ordinal`.
- `0x174140`: binds the selected page's name and enum, walks its columns, calls
  its original count/getter pair, allocates/populates the player-pointer list,
  releases previous buffers and clamps the current row. Bindings execute through
  `0x172930` / `0x1728A0`, argument expansion `0x172680`, `0x16F620/0x16F630`.
- `0x171330`: selector rendering uses the live `0x170910` count. An empty player
  list does not suppress its page: Fullbacks remains present.
- FA screen `0x362E10` restores cache `CC1C28` only below the newly counted
  length. Its producer `0x362FC0` stores `0x1706C0`'s ordinal. Native tests cover
  the last valid ordinal, one beyond it, and zero in both profiles.
- Draft/scouting `0x35FD40/0x35FD80` compare the **enum** with `CC0D44` and rebuild
  `CC00D0`/`CC0D3C` through `0x35F140`, `0x31DD90/0x31DE30`. Compaction changes
  ordinals but never that enum/cache key. Targets retain their enum-18 rule.

Twelve complete core reader spans are SHA-256 guarded before removal. The proof
CLI disassembles 36 reader functions/spans, including seven native entry points
missing from the supplied Ghidra function index. Their bounds are explicit.
Descriptor and sheet names establish routes; the two untitled comparison routes
remain named by structural context, not a claimed played screen title.

## Per-family proof and references

Every row below has the shared sequential/count/indexed readers above. The
`frame(s)` column gives every exact sheet-base reference found in the image.
The table immediately follows the sheet's fixed `0xF4` prefix. The final column
counts **raw four-byte matches** targeting all bytes in the page-family and
sheet/list spans; it does not call every integer a pointer.

Count/getter families:

- **D** `35FD40/35FD80`: draft/scouting enum-keyed cache.
- **T** `2B8D90/2B8E20`: selected team or FA; native exact-enum count/getters.
- **V** `3213E0/321520`: Pro Bowl position/conference filter, ranked top ten.
- **A** `31AB20/31AB80`: aggregate team group 9 and FA.
- **C** `36F720/36F750`: comparison team or FA.

All addresses in the table are hexadecimal. Rows are retained -> removed counts.

| Page family / selector | OLB name field; page stride | Actual table | Rows | Frames referencing sheet | Query | Raw matches |
|---|---|---|---:|---|---|---:|
| NFL Combine | 539520; C8 | 53B514 | 19 -> 18 | 53C428 | D | 25 |
| Rookie Report | 53A1F8; B0 | 53B65C | 18 -> 17 | 53C7B8 | D | 26 |
| Rookie Report, scouted | 53AF90; C8 | 53B79C | 18 -> 17 | 53C9B8 | D | 24 |
| Free-Agent Wire | 53DEF0; 118 | 53E7E4 | 19 -> 18 | 53EC10 | T | 33 |
| Player Contracts | 53FBF0; 128 | 5403CC | 18 -> 17 | 540628 | T | 2184 |
| Pro Bowl Votes | 5498E8; B0 | 54A254 | 17 -> 16 | 54AC50 | V | 28 |
| Player Progress / Preparation Results | 550F68; 110 | 5515A4 | 17 -> 16 | 5517D8, 551A18 | T | 62 |
| Opposition Study | 552798; 118 | 552F14 | 18 -> 17 | 553148 | T | 44 |
| Team Rosters, historic and team variants | 5545E8; 118 | 554D64 | 18 -> 17 | 555070, 555408, 5555D0, 555798 | T | 36 |
| Player Trade | 559450; 128 | 559B04 | 18 -> 17 | 55A0C8 | T | 151 |
| Trading Block, shared trade pages | 559450; 128 | 559C44 | 18 -> 17 | 55A2E0 | T | 152 |
| NFL Draft | 55EFB0; C8 | 55FD94 | 18 -> 17 | 5603A8 | D | 33 |
| Choose Players | 570D30; 120 | 5714BC | 17 -> 16 | 571E30 | A | 603 |
| Untitled team comparison sheets | 57FD70; 120 | 5803FC | 17 -> 16 | 580680, 580934 | C | 318 |
| Team Needs / Combine / FA companion | 582658; 120 | 582CE4 | 17 -> 16 | 582E78, 583018, 583208, 583448 | T | 54 |
| Player Trade comparison | 588060; 118 | 5887DC | 17 -> 16 | 588B60 | T | 41 |

Free-Agent Wire's Targets page retains `3630C0/3630D0`; Trade/Block's Picks
page retains `3482E0/348360`. These extra pages, All Positions and their original
orders remain intact. Special teams may be last, and SS precedes FS in several
lists: the patch preserves each list's own order.

`docs/mod_editor/nfl2k5_olb_row_evidence.json` records each original page address,
name/enum/count/getter, page-span SHA-256, every exact page-base candidate,
frame-to-screen descriptor linkage, complete before/after table bytes, every
list-interior candidate and reader-span hashes. The complete reproducible scan
found **3,664 unique raw candidates**, including unaligned windows and target
addresses inside records, fields, list entries and terminator bytes. Per-row
counts overlap where families are shared. All corpus-decoded matches in code
are instruction-encoding coincidences, not address operands into these spans.

Absolute page references are the actual selector entries, including all eighteen
shared Trade/Block entries. Additional raw page-base matches occur at `9750DF`,
`3D4150`, `AF53D3`, and `579DC`; they do not authorize moving or allocating pages.
The exact image census preserves them instead of claiming there are no references.

The small set of raw **list-interior** matches needs the same distinction:

| Source(s) | Interpretation / evidence |
|---|---|
| 4A748, 439D6, 3E7A57 | `call 4FB50`, `call 48EF0`, `call 3ED170`; the opcode plus displacement happens to encode a table address. |
| 116655 | `add eax, 5888`; the raw match includes opcode 05 and is not an address operand. |
| 4FBAC0, 4FBC88, 4FBD18, 4FBEEC, 4FBF94, 4FBFE8, 4FC060, 4FC06C, 4FC09C, 4FC0FC, 4FC15C, 4FC234, 4FC2E8 | Third words of 12-byte rows based at 4FB398. `12F160` masks/shifts these flags (at base+8) and separately dereferences the two filename pointers. These packed flag values are not page pointers. |
| 65310A, 653C1A, 81CF4A, 8FA754, A343B4 | Packed signed-short motion trajectories. Headers 653B74, 6541DC, 81D4DC, 8FB130, A347E4 respectively bound the records; trajectory strides are 6 or 8 bytes. |
| 86FC58 | Packed motion event in header 8709D4's events 86FC50..86FC68; low byte event ID, upper bits time, terminated by FFFFFFFF. |
| 43F49D | Unaligned bytes in SDK display-mode data (width/height and byte flags). No selector reader was found through this candidate. |
| AEFA7D | Unaligned overlap in a text-key/callback binding, followed by callback 364C00 and its argument. No selector reader was found through this candidate. |

The last two rows retain a narrower claim: the bytes and surrounding structure
are mapped; complete SDK/text-lookup consumer semantics were not reimplemented.
No candidate, unresolved reference or unused-looking byte was called a free cave.
This change modifies existing, actively referenced pointer tables, allocates
nothing, and proves their native consumers directly. Synthesized addresses and
unobserved runtime consumers remain a general offline-proof limit.

## PROVED: custom roster decision and receipts

The chosen custom policy is **retain/restore the row**, not merge the roster
queries. `C3CB0/C3D30`, FA `242670/242520`, draft and Pro Bowl still match enum
10 separately from enum 11. Changing only a count callback would leave getters
inconsistent. Both callbacks and every enum literal remain byte-identical.

`tools.nfl2k5_roster_reclassify.olb_filter_policy(path)` scans all 76 resources
one at a time: every primary player, including unattached FA/prospects, plus
team-referenced secondary players. It excludes only unowned secondary generation
templates. The real scan found **6,454 selectable records, 493 enum-10 records**
on retail; applying the existing recode in bounded memory leaves **zero**.
The 68 unowned main templates still include enum 10 and do not force an empty row.
Missing resources, empty scans, duplicate resources, bad references and invalid
positions cannot certify removal. Per-resource body/position hashes bind receipts
to the scanned data. ROST mutation spans and the existing writer are unchanged.

Core API:

```python
pools.apply(payload, roster_has_olb=False)  # certified zero: remove all sixteen
pools.apply(payload, roster_has_olb=True)   # known/custom/compatibility: retain or restore
pools.apply(payload)                       # new build retains; replay preserves its profile
```

The last form is intentionally idempotent. A build with incomplete scan evidence
must explicitly pass True to restore a previously removed profile, as WIRING
specifies. A later-loaded external save was not scanned: use the retained
compatibility profile for it. The patch does not dynamically detect save loads.

Exact receipt measurements on USA retail after EDGE and scheme labels, before
other owners:

| Operation | Declared edits | Changed bytes including digests | Repinned section indices | Length |
|---|---:|---:|---|---:|
| Existing retained pools profile | 46 | 655 | 0, 12, 14 | 11,948,032 |
| Retained -> removed only | 16 | 234 | 12 | 11,948,032 |
| Complete pools with removal | 62 | 869 | 0, 12, 14 | 11,948,032 |
| Identical replay | 0 | 0 | none | unchanged |

The sixteen declared tables occupy **1,200 bytes**, of which **214 data bytes**
change; the other 20 changed bytes are the existing `.rdata` digest. Section
flags remain retail (`.rdata` is 7). No runtime data is added to `.text` and no
allocation or section size changes. Retained SHA-256:
`551216bc1be3814bfc5c6d450e2788268c05010ad4e97a85af6a3637f0643242`.
Removed SHA-256:
`02c578bbb2452c0df171781a08f987c41937fa3adabb9f6cfb7387243478ce38`.
These hashes describe the stated small composition, not a release disc.

A single compacted table among retained tables, a half-edited pointer list,
nonzero trailing terminator, changed reader or foreign core site refuses before
mutation. Replaying either profile returns identical bytes, no edits and no
repinned sections. Explicit custom restoration exactly recreates the retained
profile. The old complete retained pool profile is accepted for explicit upgrade.

## PROVED: native execution and composition

`tests/nfl2k5_olb_row_fixture.py` maps the retail executable and one bounded ROST
resource, invokes real `C0500` relocation, then constructs controlled team/FA
and prospect membership from real recoded records. It runs both pooled and
custom enum-10 scenarios. The native tests cover all sixteen constructors,
all forward pages, reverse wrap and indexed restores, actual count/getter
membership, enum-keyed draft cache rebuilding, Team Rosters team AND FA selection,
empty Fullbacks, custom enum-10 pages and FA saved ordinal bounds.

The fixture supplies only bounded heap services, cell formatting/style/geometry,
visual sorting, positive equal Pro Bowl eligibility scores and the trade team's
context callback. It never replaces a selector walker, page enum binding, player
count/getter, draft cache builder or Pro Bowl position/conference filter. Thus
Pro Bowl season statistics/ranking quality and pixels are outside the claim.
Every call has a 3,000,000-instruction bound and checks stack/callee-saved
registers. Native cleanup releases every allocation; roster bytes remain unchanged.
The fixture makes `.text` RX and the selector `.rdata` pages read-only, stricter
than retail, so unintended runtime writes there fault.

Pro Bowl's four exact profiles (retail/ordered, retained/removed) compose both
ways, restore membership correctly, and replay without changes. The Practice
Squad clone accepts only the fully recognized compact source-sheet profile,
normalizing that complete span for its guard; its own replacement Active/Reserves
table is identical in either installation order.

Both XBE gates include pools explicitly. Forward installs compact before the
full allocator union; reverse installs the retained base, then compacts after
all owners. Both are byte-identical, also with explicit scale-out. Their
projection pins all sixteen full retail and final spans under the existing
pools owner, permitting only the exact Pro Bowl table overlap. The protected
release manifest and its freshness guard were not modified.

## Final verification

All listed runs passed with **no skips**. No whole disc/pack was read into RAM.
No disposable real disc was built or left behind. The largest measured test
process was about 489 MiB, below the 2 GiB limit.

| Exact command | Result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_olb_row.py` | 13 passed, 51.976 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 87 passed, 368.264 s; all four configurations; max RSS 306,064 KiB |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 103 passed, 463.158 s; all four configurations; max RSS 500,288 KiB |
| `python3 -m unittest tests.nfl2k5_position_pools_test tests.nfl2k5_roster_reclassify_test tests.nfl2k5_depth_chart_rows_test tests.nfl2k5_modern_positions_test` | 70 passed, 49.359 s |
| `python3 tests/mod_editor/test_nfl2k5_position_row_probowl.py` | 7 passed, 3.615 s |
| `python3 tests/mod_editor/test_nfl2k5_practice_squad_screen.py` | 10 passed, 104.437 s |

**290 tests passed** across the final six commands. A prior standalone pools run
also passed all 26 tests. Initial development failures were fixture/test issues:
render sorting needed a documented art stub; Picks legitimately contains 224
rows in the initialized 32-team scenario; the gate must preserve retail flags
and compare the same final roster policy. These were corrected before the final
runs; no failing safety verdict was waived.

The reference command also passed:

```bash
python3 tools/nfl2k5_olb_row_proof.py \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --corpus /home/noah/2k-football-mod-tools/research/functions/nfl2k5 \
  --output .scratch/olb-row-proof.json
```

Result: 16 selectors, 3,664 raw candidates, 36 disassembled reader spans.
Changed Python files compile; `git diff --check` passes. The full audit JSON,
exact receipts and test logs are small local `.scratch` evidence, not disc or
archive copies. The committed metadata contains no roster bodies or executable.
The candidate capability passes the registry validator's structural checks;
both module commands resolve to their declared files and every candidate
evidence path exists. The protected registry was not edited.

## HYPOTHESIS / remaining witness work

Noah's report witnesses the blank row in the prior disc, not this fix.
Rendering/layout, controller navigation through real screen transitions,
franchise save/load behavior, future generated classes and any runtime path
outside the bounded native fixture remain UNWITNESSED. No complete Build was
run because its integration and release manifest are protected handoffs.
The two untitled comparison sheets' human-facing route names remain inferred.

After protected wiring and manifest regeneration, Noah should:

1. Build a fresh pooled Experimental disc. In home-screen Team Rosters and
   franchise Team Rosters, cycle every position both directions, including
   first/last wrap. Expect one Linebackers group and no Outside Linebackers.
   Check a team with no FB: Fullbacks remains selectable and empty.
2. In a pooled franchise, repeat on the draft board, NFL Combine, both Rookie
   Report/scouting views, Free-Agent Wire/Targets, Player Trade/Picks and Trading
   Block. Verify LB player identities, All Positions, Targets/Picks and K/P.
3. Check Contracts, Player Progress/Preparation Results, Opposition Study,
   Pro Bowl Votes, Choose Players, Team Needs and both team/trade comparison
   routes. Reopen each after selecting the last group; verify cached selection,
   row cursor, sorting and wrap behavior. Check the Practice Squad screen too.
4. Use a distinguishable custom enum-10 player on a team and another in FA or
   the draft pool. Build after that custom data is installed and inspect the
   scan receipt: it must retain the row. On Team Rosters, draft, FA, trade/block
   and scouting, select Outside Linebackers and verify those player identities.
   Linebackers must still show enum 11 separately. Do not test an unscanned save
   against a disc whose receipt says the row was removed.
5. For an existing/custom roster or franchise save loaded later, build with
   Keep Outside Linebackers for existing saves enabled. Verify the row and its
   players survive save/reload. Then start a fresh pooled save on the compact
   profile, progress to another generated class and verify it creates no enum-10
   selectable players. Record this separately from initial disc scan evidence.
6. Confirm 4-3/3-4/SPECIAL assignments, ratings and on-field enum-10 alias behavior
   match the existing pool merge. BASIC still has retail OLB/ILB groups.

## Delivery

Only feature modules, policy/proof tools, tests, metadata, this report and
`WIRING.md` are delivery paths. All protected files remain byte-identical to
HEAD. `ASTRA_BRIEF.md` and `.scratch/` are excluded from staging. No push.
The explicit-path `git add -- <15 delivery paths>` was refused because the
linked worktree's `index.lock` is on a read-only filesystem. The authorized
fallback is `.scratch/r64-olb-row.bundle`, containing the explicit-path commit
on `astra/r64-olb-row` with prerequisite `12d2773`. It was created using isolated
Git metadata under `.scratch`, leaving the original branch/index unchanged.
Bundle verification, the commit ID and an exact committed-file comparison are
recorded in `.scratch/bundle-verification.json`. The bundle commits no brief,
scratch files, protected files, retail executable or roster bodies.
