# Depth locks handoff — 2026-09-05

The executable patch, record APIs, native screen setters, safety gates and
bounded execution tests are implemented in this branch. This handoff is the
remaining work in the brief's protected files. No GUI, build orchestrator,
throw-tuning orchestrator or release allowlist was edited here.

## Build integration for Claude

1. Add an experimental, opt-in `BuildPlan.depth_locks: bool = False` flag,
   availability and source-status entries, recipe serialization and receipt
   display. Use `nfl2k5_depth_locks.status(xbe_bytes)` and
   `apply(xbe_bytes) -> (bytes, receipt)`. `read_any` gives per-site diagnostics.
   Do not advertise the feature as runtime witnessed. It works with retail
   depth rows or the existing expanded rows; it requires no position split.
2. Run the patch after the shared XBE pass, position pools and depth-chart
   rows in `mod_editor/core/mod_build.py`, following the existing pure-byte
   post-passes. Feed its result into the existing XBE/section writer. Apply is
   idempotent; mixed/foreign code refuses before mutation. Enable the existing
   returner fix alongside it so unlocked CPU picks receive that bug fix too.
   Both orders with returner fix and both sides of rows expansion are tested.
3. Add the module to `packaging/release-allowlist.txt` and the relevant build
   availability/recipe tests. There is no assembler dependency at runtime:
   embedded bytes are verified against the annotated `.S` source in tests.
4. **Regenerate `data/nfl2k5_cave_reservations.json` after wiring this flag.**
   No new cave or absolute flag was allocated, but six in-place spans now
   have an additional owner and player pad byte +0x52 bits 0..4 are assigned.
   Ensure the manifest builder actually enables/observes `depth_locks`; simply
   rerunning the old preset without the new flag would miss it. The apply
   receipt declares the full span of every edit, including unchanged padding.
   Keep the oracle's source-drift check intact. Until regeneration, the old
   manifest does not describe this new stack.

   ```sh
   python3 tools/nfl2k5_cave_oracle.py manifest \
     '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
     --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
     --work-dir /tmp \
     --json data/nfl2k5_cave_reservations.json
   ```

5. Use the existing output-copy workflow. The new patch performs no file I/O.
   If adding descriptor-based XBE/disc I/O, include
   `getattr(os, "O_BINARY", 0)` in `os.open` flags on Windows; `Path.read_bytes`
   / `write_bytes` and `open(..., "rb"/"wb")` already use binary mode.

## ★ Rosters integration for Claude — no GUI edits made here

The compatibility codec key `unknown_52` is retained so existing record
imports, exports, exact round trips and diffs keep their schema. Its low five
bits are now depth locks; high bits remain unowned and untouched. Star tags
at +0x53 are independent.

```python
player.record.depth_locks
# {'rank': bool, 'side': bool, 'kr1': bool, 'kr2': bool, 'pr': bool}

document.set_depth_lock(player, 'rank', True)   # current rank, including LT/LG

document.set_depth_lock(player, 'side', True)   # current side, including RT/RG

document.set_depth_lock(player, 'kr1', True)    # transfers this team's KR1 claim

document.set_depth_lock(player, 'pr', False)    # releases a claim

document.depth_lock_conflicts(team_index)       # diagnoses duplicate imports
```

- Add a Locks column with independent Rank, Side, KR1, KR2 and PR controls,
  using the document API for writes. Display LT/LG when a T/G has rank 0;
  RT/RG when it has side 0. A player can be on both lists. Do not describe the
  two fields as a single global roster order.
- Wrap edits in the normal undo transaction. A returner role transfer changes
  its previous owner's bit too; undo must include those records. Membership
  snapshots now include locks; transfer/release/rerank clears departing
  assignments and undo restores them. Normal `to_body()` persists all bits.
- Call `depth_lock_conflicts` before saving an edited lock selection. Resolve
  imported collisions explicitly; the patch preserves conflicting locked
  rank values, and a duplicate returner claim resolves to the lowest current
  roster index. Row 7 is overflow, not a unique starter slot.
- Show a note when the target executable lacks the patch: record bits alone
  do not stop a retail executable's auto-depth. Studio returner bit edits take
  effect at the next patched compaction; this API does not immediately rewrite
  saved team returner indices. A build UI must not imply otherwise.
- The existing studio ↑/↓ API `move_in_depth` only moves team pointers. It does
  **not** set rank/side, so do not wire it as an assignment/lock control without
  actually changing the desired chain. Use the existing rank/side fields for
  assigning rows, then set the lock. Never attach a lock just to a list reorder.
- Keep an Unlock action in the studio. The game adds no new label or controller
  binding: swapping in the existing depth screen locks the changed chain on
  both participants; confirmed KR/PR choices and bench promotions lock their
  resulting assignments. Re-selecting returners transfers their claims.

Lock storage is per player, as are retail depth fields. Shared all-star player
records share their bits; a removal from any roster clears that player's
claims. A newly cloned/recreated player is not promised to inherit pad bits.

## Noah's in-game checklist

Use a disposable franchise/save and the built executable carrying the patch.
These checks are still required; no game, GUI, audio or console emulator was
launched for this work.

1. With CPU depth management enabled, move a visibly worse T into the LT
   starting row using the game's existing selection/move action. That swap
   automatically locks its rank. Put the better T at RT and move once in that
   side list to lock it too. Sim a week, inspect both rows, play a snap and
   verify identities. Repeat for LG/RG. Repeat a second week.
2. Confirm a chosen KR, then a distinct PR. The previous KR1 becomes locked
   KR2, matching the existing screen action. Sim two weeks: all three identities
   should survive roster pointer sorting. Change PR and confirm the new man
   persists; cancel a confirmation and confirm it changes nothing.
3. Promote a bench player beyond row 7 and verify the final visible row locks;
   repeat on each chain and on expanded role rows if enabled. Check screen
   navigation and rendering. Locks do not add a new in-game visual indicator.
4. Disable CPU depth management and verify the game still leaves the human
   team alone. Test a CPU team with studio-set lock bits. Unlock through the
   studio and verify the next weekly sort can choose by ratings again.
5. Trade/release a locked player. His old roster's assignment must not migrate
   to the new team; his bits clear on native roster removal. Pick a replacement.
   Test an injury and IR separately: a lock does not promise to override injury
   eligibility or keep an absent player active. Test short rosters and reserves.
6. Cross the preseason/regular-season gate and an offseason/draft transition,
   then save, exit and reload. Inspect both lock bits in ★ Rosters and visible
   assignments in game. Retirements, clones, all-star membership changes and
   third-party save tools can remove/recreate records and need separate checks.
7. Check normal KR/PR/K/P and existing SLOT/NCB/DCB rows, plus normal CPU roster
   sorting. An untouched older save begins without these lock bits.
