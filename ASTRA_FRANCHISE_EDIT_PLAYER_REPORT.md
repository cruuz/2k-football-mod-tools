# Franchise Player Contracts: Edit Player

EXPERIMENTAL / UNWITNESSED. No played-game witness is claimed.

Implemented `mod_editor/core/nfl2k5_franchise_edit_player.py`. It appends
**Edit Player** after **Assign Jersey Number**, preserving all ten existing
conditional popup records and their order. The action uses the live selected
player and the retail Rosters editor, including the existing beta-58 Position
row. The native editor retains Player Contracts, Front Office and Coach's Desk
beneath it. There is no new exit hook or runtime state.

Recommendation: **opt-in, off in Basic, Advanced and Experimental**. This adds
an unrestricted roster-editing convenience to Franchise and still needs Noah's
visual, save/reload and gameplay witness. It is not necessary to enable a
stock-feel preset. `WIRING.md` contains the complete protected-file handoff;
the standalone CLI and backend work now, while Studio wiring belongs to Claude.

## Scope and evidence

PROVED statements below mean pinned bytes, static analysis, or bounded native
execution, not an Xbox/emulator play session. The only private game input read
was the 11,948,032-byte USA `default.xbe`, SHA-256:

`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`

The Ghidra function corpus was read-only. No network, emulator, GUI display,
audio, real-disc build or archive rewrite was used. Existing Astra reports,
the RC86 changelog, Position-row implementation, Franchise Practice exit proof,
allocator, depth-lock and owner-composition evidence informed this work.

## PROVED: popup and selected player

Player Contracts is descriptor `0x540650`, handled by the native generic table
screen. `0x2B83F0` receives the manager in ECX, the table in EDX, and the selected
row index on the stack. It reads table `+0xA4` (count) and `+0x40` (player-pointer
array), puts the selected live player in EBX, and queries native pending offers
through `0x323060`. Context `DAT_00ACECD0 == 2` selects the Contracts popup arm.

The retail table at `0x521340` has ten records, stride 60 bytes. Each contains
15 dwords: UTF-16 label, action ID, three team/offer eligibility predicates,
and ten phase/retirement predicates. The native filter uses phase `0xC4BB0`,
coached-team lookup `0x13EC80`/`0xC4CA0`, the free-agent sentinel `0xACED60`,
retirement bit `player+8 & 8`, and existing offer-state bits.

| Table order | Label | Action ID | Handler |
| --- | --- | ---: | --- |
| 1 | Cancel | 7 | `0x2B8ABF` |
| 2 | View Contract | 9 | `0x2B8754` |
| 3 | Re-negotiate Contract | 3 | `0x2B8810` |
| 4 | Negotiate Contract | 5 | `0x2B8891` |
| 5 | Negotiate Contract | 6 | `0x2B8891` |
| 6 | Talk out of retirement | 4 | `0x2B8863` |
| 7 | Release To Free Agency | 0 | `0x2B8605` |
| 8 | Place on Trading Block | 2 | `0x2B8778` |
| 9 | Begin Trade | 1 | `0x2B8700` |
| 10 | Assign Jersey Number | 8 | `0x2B890B` |
| 11, appended | Edit Player | 10 | `0x2B8AB6` |

The two Negotiate actions and several other rows are mutually conditional.
The regular-season owned-team fixture produces X_Ray's seven retail rows plus
Edit Player. The new record uses current-team=1, other-team=0, free-agent=0,
and all ten phase predicates=1. Existing offer classification can suppress it,
just as it suppresses other owned-team actions. This is intentionally scoped to
the team you coach. Native filtering and every original dispatch target remain
unchanged.

The expanded action table points action 10 to the existing context-5 editor arm
`0x2B8AB6`: `ECX=manager`, `EDX=selected player`, call `0x346730`, normal return.
The Rosters callback `0x35F6C0` reaches exactly `0x346730` after its confirmation.
The new action does not create, clone, release, trade or re-sign a player.

## PROVED: all pages, Position and return

`0x346730` stores the live player at `0xCB8B14`, sets edit mode `0xCB8BA0=1`,
snapshots the parent table through `0xF33C0` at `0xCB8BBC`, and uses native face
asset lookup to select the same descriptor as Rosters:

| Page | Created-face route | Real-face route |
| --- | --- | --- |
| Identity, including Position | `0x56F6E0`, 6 rows | `0x56FD70`, 6 rows |
| Body and appearance | `0x56F410`, 5 rows | `0x56FAA0`, 3 rows |
| Equipment | `0x56F230`, 16 rows | `0x56F8C0`, 16 rows |
| Ratings | Native position-specific descriptor | Same native selection |

Real-face restrictions match Rosters; the patch does not invent face options
that retail does not offer for those players. Ratings page selection follows
the current position. Both launch routes are compared for all 17 positions,
both face cases, all descriptor addresses and every field label.

The existing Position owner inserts descriptor `0x562810` after Last Name in
lists `0x567394` and `0x5675E4`. The setter `0x345560` increments 0..16, wrapping
16 to 0; `0x345590` reverses, wrapping 0 to 16. They change `player+0x35` and the
native dirty word. `0x343460` returns early in edit mode, so changing position
does not replace the player's ratings template. No automatic depth reshuffle
is added. Existing rank/side/returner locks survive; review Depth Chart after
changing position, as with the existing roster editor.

Editor entry `0x346B90` records its initial depth at `0xCB8BA8`. START advances
through the native pages. On the last page, Finish `0x346C50` clamps birth day
via `0x346840`, runs native commit/fixup `0x343C00`, and in edit mode pops until
the recorded editor depth is gone, then restores the Contracts table through
`0xF3430`. The create-only free-agent/creation branch is not executed.

B on the first page enters `0x346D90`, pops the editor, restores Contracts, then
executes `0xF3690` to set the generic screen's extra-pop suppression flag. This
last step matters: omitting it from the initial test harness reproduced a
second pop. The corrected proof executes it natively. On later pages, B uses
retail page navigation until the first page, then returns to Contracts.

Native return chain, tested with Desk at depth 0 and 1:

```text
Main Menu (optional) -> Coach's Desk 0x522190 -> Front Office 0x52533C
                    -> Player Contracts 0x540650 -> retail editor pages
Finish or first-page Back -> Player Contracts (selected row and scroll restored)
Back -> Front Office -> Back -> retained Coach's Desk (native rows rebuilt)
```

Front Office's descriptor is also the deferred target of retail Desk callback
`0x142910`; the native Contracts push is `0x3616F0`. This path never performs
Practice's Team Select launch or its parent-discard step. A second copy of the
Practice exit repair is unnecessary. Neither fresh Franchise initialization
`0x13F1B0` nor season commit `0xC5D60` is reached.

**Back is not undo.** Retail changes the live record immediately. A position
change remains after Back and reopening selects the same record.

## PROVED: contracts, cap and locks

The native fixture starts from the existing bounded synthetic Franchise save,
relocates the roster through native `0xC0500`, and chooses the second player
rather than assuming row zero. Nonzero contract fields, pending-offer state,
league salary cap (80,500 at native `0xE3C278`), depth-lock byte `+0x52`, ability
byte `+0x53`, team arrays, other players and season globals are snapshotted.

Controller bindings execute native setters for Position (`+0x35`), Height
(`+0x2B`), Helmet (`+0x0C` bitfield) and Speed (`+0x36`). The entire synthetic save,
season block and live Front Office range are compared after Finish/Back.
Only the specifically edited record fields differ. The memory-write trace also
permits the native birth-day clamp's unchanged dword write at `player+0x18`.
Position cycling in both directions preserves every other record byte; undoing
the cycle restores the complete record. The complete allocator-owner stack
plus the existing depth-lock patch runs the same open/edit/return tests.

This proves preservation for those bounded cases. It does not claim every
possible name, jersey, contract, malformed record or save/reload combination.
Native Rosters fixups remain authoritative for other fields, including speech
IDs and jersey conflicts. Saving and reloading an actual Franchise is on Noah's
witness list.

## Implementation, integrity and allocator

Only 37 complete native instructions change, with identical instruction lengths.
The popup stack grows by 8 bytes (`0xA4` to `0xAC`), its selected-index argument
moves `+0xB0` to `+0xB8`, and zero initialization grows from 22 to 24 dwords.
This accommodates eleven `(label, action)` pairs plus a full zero terminator.
All 17 epilogues are updated, including other contexts of this shared callback.
A disassembly census checks every stack return and every old row-table reference.
The filter loop bound becomes 660 bytes and the action bound becomes 10.

Allocation request:

```python
REQUESTS = (("nfl2k5_franchise_edit_player", "read_only", 704, 16),)
```

660 bytes of rows plus 44 bytes of dispatch targets. No new executable code,
RW allocation, save field, heap code or runtime data in `.text`. The original
row table remains intact. The v3 XBE remains 12,300,288 bytes. The budget fixture
contains 45 input requests; its plan includes the existing boot-logo request
for 46 total, with 7,400 bytes available for further RO allocations; RX/RW
headroom remains 52,624 / 4,096 bytes. No allocator page count is extended.
This new feature had no earlier planned budget row; its actual 704-byte RO
request was added within existing general RO capacity.

`status` reports retail/applied/foreign. `apply` validates complete instruction,
table, prerequisite, digest and allocator-seal state before any writer is used.
It installs the existing Position owner as a dependency, pins its full descriptor
and native setter/guard routines, and rejects missing or partial dependencies.
Replay is byte-identical with zero changed bytes. Receipts include exact edits,
allocation/dependency receipts, SHA-256 hashes and changed-byte counts. A grown
image without this owner's preallocated union refuses before dependency writes.

Shared MyCareer screen/editor hooks and playlist dispatcher hooks are accepted
only when their entire existing owner installation validates; only their exact
sites are normalized for native prerequisite hashes. Both legacy and generic
MyCareer formats are recognized. Their modules were not edited.

CLI (new output only, bounded 16 MiB input, no overwrite):

```text
python3 -m mod_editor.core.nfl2k5_franchise_edit_player status source.xbe
python3 -m mod_editor.core.nfl2k5_franchise_edit_player apply source.xbe contracts-editor.xbe
```

The complete gate union, both explicit gate owner checks, pairwise matrix,
allocator budget, dormant union and manifest observer/owner lists include this
owner. No protected file was changed. The release manifest remains stale on
this base and must be regenerated by Claude after product wiring.

Local gates use `NFL2K5_CAVE_MANIFEST=.scratch/franchise-edit-player-manifest.json`.
This is a copy of the existing reservation document with current source pins,
not a newly observed disc manifest. Eight recorded files had source drift:
`mod_build.py`, `nfl2k5_throw_tuning.py`, `nfl2k5_espn25_rosters.py`,
`nfl2k5_my_career_mode.py`, `nfl2k5_my_career_mode_code.py`,
`nfl2k5_read_option_runtime.py`, `nfl2k5_read_option_runtime_code.py`, and
`nfl2k5_xbe_space.py`. Only the last file was changed by this task, to add the
new dormant request. The other seven were already different on this base.
The new owner's source pin was added. All 145 scratch source fingerprints match the final sources. Strict source validation remains enabled;
only the disposable manifest has refreshed hashes. Both gates derive the
actual sealed allocation union and project exact new instruction reservations,
checking retail/applied pins and other-owner overlap. The protected release
manifest and all other protected files match HEAD.

## Validation results

Commands below use Python 3.12.3, Unicorn 2.1.4 and Capstone 5.0.7 on Linux.
Each suite is a standalone unittest script. Missing private XBE, Capstone or
Unicorn yields a precise skip for dependent evidence. Each native call is
bounded to 300,000 instructions; row navigation is also capped by the row count.
The synthetic save is under 1 MiB, the native heap is capped at 1 MiB, and prior
Unicorn callback cycles are collected before mapping each next case.

All measured commands used `/usr/bin/time -v`. Logs and the scratch manifest
remain in `.scratch/` and are excluded from the commit. The initial integrity
and phase-matrix failures described below were corrected before these results.

| Command (prefix `python3`) | Result | Seconds | Peak RSS (MiB) |
| --- | --- | ---: | ---: |
| `tests/mod_editor/test_nfl2k5_franchise_edit_player.py` | 12 passed | 41.508 | 149.1 |
| `tests/mod_editor/test_nfl2k5_franchise_edit_player_unicorn.py` | 8 passed | 309.092 | 194.1 |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed | 407.821 | 889.9 |
| `tests/mod_editor/test_nfl2k5_allocator_scaleout.py` | 23 passed | 965.639 | 196.6 |
| `tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 130 passed | 1515.821 | 187.5 |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 99 passed | 1809.545 | 332.9 |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 111 passed | 2034.405 | 514.4 |

All seven complete suites pass: **411 tests, no skips or failures**. The largest
process was the oracle at 889.9 MiB, below the 2 GB limit. The safety gates,
pairwise, oracle and allocator commands ran with the scratch-manifest environment
prefix shown above. No protected source or release manifest was edited.

The final navigation subset passed **2 tests in 261.230 seconds**, peak RSS
194.1 MiB, after bounding the fixture's outer navigation loop. Exact command:

```text
python3 tests/mod_editor/test_nfl2k5_franchise_edit_player_unicorn.py NativeTests.test_controller_edits_position_appearance_equipment_ratings_and_finishes NativeTests.test_position_cycles_all_seventeen_both_directions_without_template_reset
```

 Both gates exercise forward/reverse orders
and automatic/explicit v3 selection with every owner. Pairwise also includes
both mutually exclusive MyCareer formats as separate partner cases.

`python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json`:
PASS, 46 requests, unchanged 12,300,288-byte XBE size, no build.
`python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py PlannerTests`:
5 passed, 0.857 seconds. CLI help, source compilation, strict new capability
schema/path/module checks, source-pin verification and `git diff --check` pass.
The protected release manifest has not been regenerated or modified.

## HYPOTHESIS and known gaps

The bounded proofs support a normal in-game row and return flow, but the popup's
visual size, text rendering, controller feel, preview assets and long-session
behavior remain unwitnessed. The modal service selects from the real native
filtered rows; it does not draw a popup. It asserts the full bounded terminator.
The fixture executes screen push/pop/event handlers, row binding, native table
construction, field setters and return restoration. It substitutes heap,
controller hardware, text/title confirmation, rendering/layout/sorting, and 3D
preview services. The preview camera `0x346890` is substituted; editor entry
`0x346B90`, which captures the return depth, executes natively. Front Office
begins with a completed fade, as on an already-open Contracts screen. Companion
hooks execute in the composed fixture, but active MyPlayer and music playback
sessions are not simulated. Native sorting is a fixture service; the proof
checks cursor restoration, not every possible reordered/filtered list after a
name or position edit.

An initial draft transposed a phase bit in retail Negotiate action 6. Both the
byte-for-byte row assertion and native phase matrix caught it; the final table
matches all 600 original bytes. Initial harness failures also caught the face
variant flag assumption, a legitimate empty popup for other teams in phase 6,
and the difference between write history and a restored final position value.
The allocator regression assertions were updated for the exact 704-byte RO
headroom reduction. No game module was weakened to accommodate a fixture.

No generated disc, real console boot, archive mutation, signed-save operation,
season simulation, or entire-game integrity claim is made. A capacity check
reported about 93 GiB free on `/`, already below the 100 GB working target;
this task created no disposable disc and its scratch evidence is under 4 MiB. The feature is
labelled EXPERIMENTAL / UNWITNESSED in the backend help and capability handoff.

## Noah's witness list

1. Build a clean image with this opt-in and the normal beta-63 stack. Load a
   backed-up Franchise; open Coach's Desk, Front Office, Player Contracts.
2. Select T. Houshmandzadeh or another nonfirst player. Confirm the seven native
   actions remain and Edit Player is last, after Assign Jersey Number. Verify
   labels, popup bounds and controller selection. Check another team's screen
   and Free Agents retain their native actions without the new row.
3. Open a player with a real face and one with a created face. Check every page
   and preview against Rosters. Edit appearance, equipment and a rating. Verify
   Position appears after Last Name and cycles through all positions.
4. Record salary/cap, contract years/bonus, depth ranks/side/returners and ability
   bits first. Change position, Finish, and confirm those values and other
   players are unchanged. Inspect Depth Chart before playing.
5. Finish from the last page and verify Contracts restores its selected player,
   tab and scroll. Repeat with B on each page; first-page Back returns to
   Contracts and retains edits. Reopen the player and verify the changes.
6. Back out of Contracts to Front Office and then Coach's Desk. Confirm the Desk
   remains interactive and no Main Menu return occurs. Repeat several times,
   including after Franchise Practice and with Auto Save/MyCareer enabled.
7. Save manually, quit, reload and verify the intended edits, contracts, cap,
   depth locks, pending offers and season week. Play/practice a rep using the
   changed position. Check postgame and subsequent contracts/depth screens.
8. Try preseason, regular season, playoffs, offseason, retirement and a pending
   negotiation. Confirm existing transaction actions still behave normally.
   Keep experimental default-off until this witness is recorded.

## Delivery

Committed on `astra/r65-franchise-edit-player` using the 15 explicit feature,
proof, allocator-registration and handoff paths. The normal worktree index was
writable, so a bundle fallback was unnecessary. `ASTRA_BRIEF.md` and `.scratch/`
are excluded. No push was performed. Final whitespace checks and a comparison
of every protected file against HEAD passed. Scratch receipts/logs total under
4 MiB; no executable, pack or disc copy remains there.
