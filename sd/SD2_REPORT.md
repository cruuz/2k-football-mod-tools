# PROVED OFFLINE: SD2 finite CPU lineup traversal

**DESIGN:** SD2, 2026-09-28. Labels apply to the paragraph, list, table, or code block they introduce. PROVED OFFLINE means source, inspected bytes, or native offline execution, not an in-game witness. DESIGN describes implementation choices or the main-only lab. INFERRED identifies conclusions beyond the available artifacts. This continues private branch `job/b76-sd`, including SD1 commit `11af6c47`, from worktree base `9de33371`.

**PROVED OFFLINE:** The production repair terminates the captured D lineup call and fills all 11 slots with distinct non-null players. The unchanged capture loops. The fix is mandatory inside `position_pools.apply`, including both optional-code configurations and retained OLB selectors. Candidate D's actual executable reports `needs_fix`; an in-memory application reports `applied` and changes only the iterator allocation and its `.text` digest. No disc was written. [Captured replay](sd2-evidence/replay.json), [D upgrade receipt](sd2-evidence/disc-upgrade.json).

## PROVED OFFLINE: alias audit

**PROVED OFFLINE:** The complete native pair table and all 19 fallback rows are recorded in [alias-audit.json](sd2-evidence/alias-audit.json). The fallback table begins at `0x4F5A38`, with 76-byte rows; kind 14's row is `0x4F5E60`. Exactly one pair-table site is rewritten by the pool module: `olb_kind_lists`. The other pool changes affect roster classification, depth-chart consumers, ratings, and labels rather than introducing additional physical list aliases.

**PROVED OFFLINE:** The following audit concerns valid native roster lists. A malformed arbitrary memory image is outside the proof. Two chains of the same kind are alternative ranked views, selected by the slot's rank parity, rather than two consecutively scanned pools.

| Consumer or pool | Pair / change | Unfixed exhaustion result and fixed treatment |
| --- | --- | --- |
| LB kinds 14 and 15 | Kind 14 remains `(17,18)`; kind 15 changes `(15,16)` to `(17,18)` | New cross-kind alias. A returned enum-10 or enum-11 player resolves to kind 14, losing which fallback occurrence produced it. The fixed cursor is the player itself in a reconstructed ordered stream. |
| Kind 14 primary | Fallback starts `14,15,17,16,13,...` | Exhausted kind 14 restarts through kind 15. Captured D cycles. Fixed visits the selected LB chain once and returns null. |
| Kind 15 primary | Fallback starts `15,14,12,18,16,...` | With both LB bits allowed, searching by kind 14 resumes at the second occurrence. With only bit 15 allowed, the old routine prematurely exhausts after one LB. The 46-byte proposal also returns only one. Production enumerates all five, in the primary chain's order, then null. |
| Other primary kinds | Every fallback row contains 14 and 15 | Rows 11 and 13 also place 14 before 15. Native all-allowed replays cycle for primary kinds 11, 13 and 14, on both chains. Rows placing 15 first do not cycle in that replay but can lose order/candidates when resumed by enum. Production keeps the original row order and mask passes. |
| EDGE, kind 12 | `(11,12)` unchanged | Reclassification moves edge players into this existing kind. No new pair alias. An EDGE slot can still reach the LB defect through fallback under an appropriate mask/tier. Physical dedup covers that path. |
| Interior DT/NT, kind 13 | `(13,14)` unchanged | Multiple depth slots share this existing pool with different rank/chain selectors. This is not a cross-kind pair alias. Its fallback row does encounter LB 14 before 15, and the old replay cycles. |
| Remaining native kinds | `(0,0),(23,23),(24,24),(25,25),(26,27),(6,7),(10,10),(8,9),(3,3),(4,5),(1,1),(2,2),(19,19),(20,20),(21,22)` | No pair rewrite. Equal entries within one pair select one list, not two iterations. Primary-only kinds 3/4 retain their native exclusion from other kinds' fallback scans. Their special lists can contain players also in ordinary lists; the player bitmap prevents duplicates across those different physical lists. |
| Empty pools | Native counts zero / terminator `0xFF` | No player can restart an empty list. Existing loops are finite for entirely empty input. The repair also returns null; no stale cursor or persistent visited state. |
| All tired / all assigned | Eligibility and lineup membership are checked by the caller | They do not change the iterator's inputs or list ordering. They force the caller to consume its whole stream. Original aliases can cycle indefinitely; fixed exhaustion permits the existing caller relaxation. |

**PROVED OFFLINE:** The old 46-byte proposal is insufficient as a general repair: for a kind-15 primary, rank 1, mask `0x8000`, it returns Edmunds then null. The replacement returns Edmunds, McFadden, Reese, Kelly, Barnes, then null. This is an explicit counterexample to preserving the entire unified primary pool, even though the narrow proposal fixes captured D. No fallback row, pair, rank encoding, or mask table is rewritten by the production repair.

**PROVED OFFLINE:** `position_pools_keep_olb=True` is currently rejected by Studio's builder with its existing EDGE-only compatibility message. The lower-level `pools.apply(roster_has_olb=True)` retained-selector API remains supported. The new repair applies there as well. Selector retention never changes the gameplay enum bridge: enum 10 and enum 11 both map to kind 14. The sweep covers modern enum-11 LBs, mixed enum-10/11 LBs, and all-legacy enum-10 LBs on those merged chains. Selector visibility for external saves remains the existing separate product limitation; this fix does not re-enable the deprecated build switch.

## DESIGN: production implementation and integration

**DESIGN:** [nfl2k5_lineup_iterator.py](../mod_editor/core/nfl2k5_lineup_iterator.py) replaces `0xE8410..0xE878F` in place. Its 393 instruction bytes are padded to the owned 896-byte function span. EBP anchors 112 local bytes, including one list bitmap and a 256-bit roster-index bitmap. The fastcall arguments, callee stack cleanup and nonvolatile registers are preserved. No new global data or cave is needed.

**PROVED OFFLINE:** Traversal reconstructs the same deterministic stream on each call: original fallback row, original slot rank passed to `0xE7530`, allowed-mask pass first, then the non-allowed pass for relaxed tiers. Tier zero remains primary-only. The native list-count and start-index helpers remain in use. A list is marked after mask classification, so an allowed alias takes precedence over a disallowed alias without changing the row. Each roster index is marked before advancing past the current player. This preserves ordering while preventing restart through an alias or repetition through a special list. The first-candidate routine and fatigue/assignment predicates are untouched.

**PROVED OFFLINE:** For stable valid inputs the stream is finite: at most 19 row entries per pass, each selected physical list scanned once, each byte-sized roster index emitted once, and null after the last candidate. The 53-player capture therefore requires at most 54 iterator/initial-candidate calls through exhaustion. Every tested call completes below the explicit 100,000-instruction replay limit. An additional 1,568 complete scans measured a maximum of 4,983 instructions and 17 physical list visits, with no duplicate list visits. [Instruction counts](sd2-evidence/instruction-bound.json).

**PROVED OFFLINE:** With `position_pools` off, the repair writer is not called. The existing `if plan.position_pools` build gate is retained, there is no automatic upgrade of an old image when the option is off, and the optional extent guard is read-only. Thus this change introduces no XBE mutation on the off path. Healthy first-candidate selection is byte-identical because that routine is unchanged. Six complete rested-lineup replays also match the old output exactly. This is a bounded normal-case witness, not a claim that defective old fallback behavior is preserved for every possible roster.

**PROVED OFFLINE:** Status now distinguishes `retail`, `needs_fix`, `applied`, and `foreign`. Only a complete prior pooled profile with the exact old iterator is upgradeable. Partial/foreign repair bytes refuse before mutation. Upgrading without changing selector policy writes one site; repeated application makes zero edits. Studio Build and Gameplay Patches enable an upgrade row with “Needs CPU lineup fix.” Source readers, roster scheme detection, MyCareer, SPECIAL row dependencies, editor/filter companions, and modpack recipe inspection retain the identity of an older pooled disc. The capability registry and existing write-evidence metadata include the new repair. Provider source pins include both new helpers; the exact 331-module closure check passes.

**DESIGN:** Main must regenerate the protected cave manifest last on the integrated stack. Required new reservation: owner `nfl2k5_position_pools`, half-open VA span `[0xE8410,0xE8790)`, size `0x380`, basis `declared edit: lineup_iterator`. The existing receipt observer already records the full allocation, including padding. No allocator request is added. The current manifest has no overlapping owner; it was not regenerated here. Section digest repair uses the existing owner machinery. [Reservation audit](sd2-evidence/reservation.json).

## PROVED OFFLINE: validation

**PROVED OFFLINE:** [replay_sd2.py](replay_sd2.py) executes native instructions and lazily maps supplied capture pages. No game callee is mocked. It reads `main/stall-candD/watch-end.bin` through the shared harness's page-table decoder and never starts xemu.

| Proof | Result |
| --- | --- |
| Captured D, unchanged | Continues cycling; does not reach the outer return in the bounded replay. |
| Captured D, production bytes | Reaches `0x18A7A7` in 15,659 instructions; 11 distinct non-null players; slot 6 is McFadden after native tier relaxation. |
| Complete rested lineups | Six equal before/after results: modern, mixed and legacy LB enums, each with kind-14 and kind-15 primary descriptors. |
| Captured-memory sweep | 26,880 cases; all 19 kinds; ranks 0..3; tiers 0,1,2,6; primary, full, LB14-only, LB15-only, both-LB and zero masks, deduplicating equivalent mask cases. |
| Pool states | Rested, tired, assigned, mixed, empty; all terminate; at most 53 distinct candidates. |
| Native-helper model sweep | All 19 kinds, all eight encoded ranks, all seven tiers, both populated and empty lists, mask variants, mixed OLB/LB and overlapping special lists. Every emitted successor matches an independent ordered-set model. |
| Repository suites | 76 production/native/composition tests, one GUI upgrade test, four extent tests, three lab decoder tests, one exact provider-closure test pass. |

**PROVED OFFLINE:** In the capture sweep, rested/tired/mixed states write native energy fields; empty clears native list extents. “Assigned” consumes and rejects every returned candidate as the caller membership predicate would. The iterator takes no lineup or fatigue argument, so its finite-stream proof also covers every assignment/rejection combination without fabricating a 53-entry active lineup. The separate captured full-caller replay supplies the actual native assignment and fatigue predicates. Logs are in [sd2-evidence](sd2-evidence). The initial pool run caught the now-updated write-evidence metadata; the final 76-test run passes. Registry validation and its seven schema tests also pass.

**DESIGN:** Reproduce the principal checks from the integrated checkout, after the shared builder has exited:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 sd/replay_sd2.py --sweep
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.nfl2k5_position_pools_test tests.mod_editor.test_nfl2k5_position_choices tests.mod_editor.test_nfl2k5_olb_row tests.mod_editor.test_nfl2k5_lineup_iterator tests.nfl2k5_depth_chart_rows_test -q
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 -m unittest tests.mod_editor.test_nfl2k5_lineup_status_qt tests.mod_editor.test_nfl2k5_lineup_lab tests.mod_editor.test_nfl2k5_disc_extents -q
```

## DESIGN: main-only forced-fatigue lab

**DESIGN:** Run `bash sd/lab/sd2_cpu.sh` after integration. It uses the shared k1 harness through r1's CPU-v-CPU Quick Game route, GIANTS versus COWBOYS. It holds `flock /home/noah/2k-worktrees/.b76-session/xemu.lock` across both arms, waits for the shared build and existing xemu to exit, and uses stock flatpak, 128 MB, loopback-only gdb and QMP, a per-run HDD overlay, and D's explicit `:ro` grant. D's size and complete XBE hash are checked. Runs, frames and logs stay under `/media/noah/Storage/.b76-research/sd/lab/`. Large RAM snapshots are disabled; frames are retained. Neither script nor offline validation was used to launch xemu here.

**DESIGN:** After the intro, gdb stops at `0x18A6B2`, before native lineup eligibility checks between plays. It requires a defensive descriptor with LB slots, derives the defending roster through the pinned `0x61C70/0x61C80` getter, and walks its player pointers. Only enum 10/11 energy floats are changed, via `[ [player+0x30]+4 ]+4`. All addresses, thresholds and original energy values are validated before the first write. Writing 0.0 rejects both active and inactive LBs under D's 5/20 and 16/20 thresholds. Five captured LBs were independently decoded and rejected by native `0x188440` after these exact writes. [Decode proof](sd2-evidence/force-decode.json).

**DESIGN:** The control arm keeps D's original iterator. Within 60 seconds after forcing, gdb must observe three repeats of the same candidate cycle at caller `0x1894B3`, with the same stack, descriptor, slot and tier. This directly identifies the `0xE8410` retry loop. It does not infer freezing from one repeated PC. The fixed arm guards then writes the production repair into guest RAM after boot, applies the same forcing operation, and requires 180 seconds of continued play, multiple completed lineups including one after 150 seconds, and changing retained frames in each minute. No controller nudges occur during this observation. A missing force, foreign guard, failed control, timeout, xemu exit, or missing progression fails the arm and retains diagnostics. These are planned acceptance criteria; no in-game PASS is claimed.

## PROVED OFFLINE and INFERRED: public exposure

**PROVED OFFLINE:** Current Studio presets and inspected tags beta-54, 61, 65, 70, 74 and 75 all set BASIC off, ADVANCED on, and EXPERIMENTAL on. The committed export recipe uses those same presets and names the beta-60 family as below. The only committed `.2k5patch` files in this checkout are explicitly synthetic legacy test fixtures, so they cannot certify published asset hashes. [Exposure receipt](sd2-evidence/exposure.json).

| Preset / recipe family | `position_pools` | Exposure |
| --- | --- | --- |
| BASIC / `SOFTDRINK-patch-basic-v0.9.2k5patch` recipe | Off | Does not introduce this alias when applied to retail. |
| ADVANCED / `SOFTDRINK-patch-advanced-v1.2.2k5patch` recipe | On | Carries the unfixed alias in pre-SD2 builds. |
| EXPERIMENTAL / `SOFTDRINK-patch-experimental-v0.5.2k5patch` recipe | On | Carries the unfixed alias when that family was exported. The local changelog explicitly says beta 61 shipped without an Experimental export. |

**INFERRED:** Users of pre-fix ADVANCED/EXPERIMENTAL releases, custom builds that enabled the checkbox, or discs inheriting those bytes are exposed. Selecting BASIC on an already pooled source does not remove the installed alias. Existing opaque `.2k5patch` artifacts do not acquire this repair merely because Studio is upgraded; main needs fresh exports or an explicit upgraded build. The affected family follows directly from the presets/export recipe; the exact public asset/version inventory and downloaded-file hashes were not independently verified. No release work was performed.

## PROVED OFFLINE: optional extent guard and delivery

**PROVED OFFLINE:** Separate commit `9d4a4ded` adds [nfl2k5_disc_extents.py](../mod_editor/core/nfl2k5_disc_extents.py) and the final build gate. It checks every parsed directory/file plus the root, uses Python wide arithmetic with explicit field and capacity bounds, validates rounded sector ends and absolute ends, and rejects lengths above `0xFFFFF800`. It uses the conservative signed-LBA ceiling from SD1, not a 4 GiB or guessed 7 GB image limit. Boundary tests cover 2/4 GiB crossings, the final sector, rounding overflow and unrepresentable fields. D's 8,012,931,072-byte image passes all 21 extents read-only. [Extent receipt](sd2-evidence/disc-extents.json).

**PROVED OFFLINE:** The principal repair is commit `085fcdc5`; the separate guard is `9d4a4ded`; provider dependency pins are updated after both. All commits use explicit pathspecs and the requested Astra coauthor trailer in the existing private repository. The shared worktree Git HEAD remains `9de33371`. No push, tag, full build, xemu session, or write to D or another worktree was performed. Longer test runs started only after the builder process check was empty; no process pool or multi-gigabyte workload was used.

**DESIGN:** Delivery bundle: `/media/noah/Storage/.b76-research/sd/astra-build/sd2.bundle`, with verification/import hashes and final commit IDs in the adjacent `sd2-delivery.json`. It includes SD1 and SD2 relative to `9de33371`. Main should integrate the private commits, regenerate the cave manifest last, then run the forced-fatigue A/B before treating this as witnessed in game.

## PROVED OFFLINE / DESIGN / INFERRED: 15-line summary

1. PROVED OFFLINE: D's freeze is the alias-driven CPU lineup cycle, reproduced again.
2. PROVED OFFLINE: Only kind 15's physical pair is rewritten; it aliases LB kind 14.
3. PROVED OFFLINE: Fallback rows 11, 13 and 14 reproduce cycles when rejection consumes their streams.
4. PROVED OFFLINE: Kind-15 primary with mask 15 alone defeats the narrow proposal's coverage.
5. DESIGN: The production iterator reconstructs ordered candidates with list and player bitmaps.
6. PROVED OFFLINE: Primary rank selection, mask priority and native tier relaxation remain intact.
7. PROVED OFFLINE: Captured D returns with 11 distinct players in 15,659 instructions.
8. PROVED OFFLINE: All 26,880 captured-memory sweep cases terminate without duplicate players.
9. PROVED OFFLINE: Six complete rested lineups equal their pre-fix results.
10. PROVED OFFLINE: Old discs read needs_fix; fixed discs read applied; foreign bytes refuse.
11. DESIGN: Main reserves 0xE8410..0xE878F during the final manifest regeneration; no new cave.
12. DESIGN: Main runs the supplied locked, read-only-disc, RAM-repair forced-fatigue A/B.
13. INFERRED: Pre-fix Advanced, Experimental and custom pooled discs expose their users.
14. PROVED OFFLINE: The separate wide-arithmetic extent guard passes D and its boundary tests.
15. DESIGN: Import the verified private bundle, integrate, regenerate the manifest, then witness in game.
ASTRA_DONE
