# r62 read-option / screen-hooks composition repair

2026-09-06. Branch `astra/r62-readoption-screenhooks-compose-fix`, base
`c80976907da4735f1991566fd696d2b5768a647e`.
**EXPERIMENTAL / UNWITNESSED.** No gameplay, game/console emulator, display,
audio, network or push was used. Unicorn ran bounded instruction fixtures only.

The mutual refusal at `0x19C740` is fixed. Both owners install in either order,
produce identical bytes, and replay exactly at pair-only and complete-union
allocation addresses. **The two full XBE gates are still blocked by the separate
MyCareer/playlist/Practice Squad composition issue named in the brief.** This
delivery does not claim that the complete stack passes either gate.

## Built and decisions

- Split each owner's inspection into ownership validation and dependency
  validation. Public status/apply still first validate geometry, section
  digests and allocator seals. Ownership validation checks the exact allocated
  code, all hooks and, for read-option, initial RW, paired table and prompt.
- A nonretail partner hook is accepted only after that complete owner passes.
  Both dependency sets are then checked against their original SHA-256 pins,
  normalizing only already validated hook spans. No arbitrary jump target,
  padding, code body or byte beside a hook is normalized. The two inspection
  phases avoid recursive status calls, including Spy's existing call into
  read-option status for lifecycle compatibility.
- Kept both native hook sites, all assembly/templates, runtime policies,
  receipts, feature versions and REQUESTS. No new code, data, section, cave,
  runtime allocation or policy tuning is introduced.
- Corrected only the read-option rows in the budget fixture: its inherited
  v1 `960 RX / 64 RO` rows contradicted the landed v2 module and its existing
  test. They now list the already implemented `2048 RX / 256 RW / 88 RO`, all
  aligned to 16. The screen owner remains 640 RX bytes. The 38-row fixture
  still plans successfully, with 4,096 contiguous RW bytes available.
- Added the standalone focused regression suite
  `tests/mod_editor/test_nfl2k5_read_option_screen_hooks_compose.py`. The shared
  stack helper, both gates and the manifest builder already enumerate both
  owners and use their live REQUESTS; no duplicate installation was added.
- Added a precise integration note to `WIRING.md`, including the now shared
  runtime module closure and the manifest/companion-repair prerequisites.
  No protected file or separately assigned implementation was edited.

## PROVED: native boundary and offline behavior

The read-only Ghidra ledger identifies `FUN_0019c740` as
`0x0019C740..0x0019C852`, 275 bytes. Its decompilation is in
`research/functions/nfl2k5/pseudo_c/shard_007680_008191.c:4415` beneath the
read-only corpus root. It assigns the pass timer before the final callback.
Capstone disassembly of the pinned USA XBE confirms these complete instructions:

| Owner | Hook | Retail bytes | Continuation |
| --- | --- | --- | --- |
| Screen hooks | `0x19C7E9`, load stack-local timer and store task `+0x60` | `8b4c240c894e60` | `0x19C7F0` |
| Read-option v2 | `0x19C849`, store native callback `0x19BB60` | `c70660bb1900` | `0x19C84F` |

These spans do not overlap. Screen hooks returns before the native callback
assignment; read-option runs at that later assignment and preserves the timer.
Both guards retain the full 275-byte retail hash
`661ab0647ceb5ff1e2243adccfc36dba60829f8d04caede6d74c2db0f86dab72`.
Before editing, a direct pair reproduction produced the brief's exact
`ScreenHooksError` and `ReadOptionError` at `0x19c740` in the respective orders.

The new tests prove within bounded fixtures:

1. Pair-only and complete-union allocations differ, both orders yield identical
   bytes, and status/settings/replay remain valid. Replay returns the same
   object, `already_applied`, zero changed bytes and no edits. Partner-only and
   reserved-but-uninstalled partner states work. Normalizing just the two
   shared spans recovers every retail byte of the complete routine.
2. A changed opcode, any displacement/padding byte, either adjacent byte or
   the routine's first byte refuses before any allocator/install call.
   Exact-looking detours without the named allocation or code, missing other
   partner hooks and a wrong destination within owned RX also refuse.
3. Foreign code and padding, invalid table/prompt, nonzero initial RW and
   unrelated partner dependency changes refuse. Tests deliberately reseal code
   and RO mutations and repin section digests: valid checksums do not authorize
   foreign owner bytes. The allocator independently rejects nonzero initial RW.
4. Spy plus both owners applies and replays in forward/reverse order without
   recursive status validation.
5. With both hooks installed, ATL178's matched default screen timer stays 0.6,
   an ordinary ATL177 pass keeps its supplied 1.0 timer, and the later
   read-option hook retains the native callback when no RPO latch is live.
6. An authored Shotgun RPO runs through the real full pass initializer and
   enters both installed detours in each installation order. A ready receiver
   reaches callback `0x19BAE0`, is retained in task `+0x40`, and causes native
   command `0x42` to be stored. An unready receiver falls back to `0x19BB60`.
   The latch is consumed once; omitted-table replay preserves the authored
   table, and a changed explicit table refuses.

The native fixtures reuse the existing real PLAY loader and instruction
ceilings. The RPO task-allocation and aiming-result boundaries remain the
documented synthetic ABI boundaries. No animation, contact, ball flight,
catch, GPU output or live game loop is proved.

## Complete-union evidence and remaining blockers

Both unmodified XBE gates were run after the guard fix. Each reaches beyond
the repaired pair and then reports four setup errors:

- Forward and explicit-scaleout forward: all owner apply calls finish, but
  `compose` rejects `nfl2k5_music_playlist` during complete-owner replay.
- Reverse and explicit-scaleout reverse: the Practice Squad screen installer
  refuses `apply practice squads, Franchise Practice and practice reserves
  first` after MyCareer has changed shared screen dispatch. The reverse union
  does not finish installing its remaining owners.

The unmodified Spy suite also reports the same forward-union playlist failure.
The brief explicitly assigns that repair elsewhere and forbids editing
MyCareer, playlist and Practice Squad screen here. No owner was omitted,
guard bypassed, gate mocked, test skipped or expected failure substituted.

A separate bounded diagnostic invokes the real `tests.nfl2k5_allocator_stack.compose`
in both orders and inspects its exception frame without modifying execution.
At each real stop, both read-option and screen-hooks report `applied` and each
replays to the identical payload object. Forward has applied every owner;
reverse has not. The exact states, addresses, hashes and stopped owner are in
`.scratch/readoption-screenhooks-compose-fix/union-inspection.json`, with its
reproduction script beside it. This is evidence for this pair inside the
attempted full union, **not a passing complete-union gate**.

The existing screen-hook manifest test independently refuses
`stale reservation source: mod_editor/core/nfl2k5_hires_pack.py`. Comparing
manifest fingerprints to base-commit blobs confirms six inherited stale
sources: hires_pack, hires_texture, play_library, qb_spy_runtime,
read_option_runtime and read_option_runtime_code. This change also invalidates
screen_hooks.py. The protected manifest was not edited, refreshed manually or
replaced with an unproved scratch projection. Claude must regenerate it after
merging the companion repair and final sources, then rerun both full gates.

## Exact validation results

Commands are relative to the repository root, with `python3 file.py` standalone
unittest execution. No evidence/dependency skips were needed. Logs are under
`.scratch/readoption-screenhooks-compose-fix/`. Times are unittest elapsed
seconds; RSS is `/usr/bin/time -v` maximum resident KiB.

| Command | Final result | Seconds | Peak RSS KiB |
| --- | --- | ---: | ---: |
| `python3 tests/mod_editor/test_nfl2k5_read_option_screen_hooks_compose.py` | 9 passed | 61.849 | 210,608 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_runtime.py` | 10 passed | 6.952 | 130,196 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_controls.py` | 15 passed | 14.982 | 177,520 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_unicorn.py` | 14 passed | 15.118 | 165,264 |
| `python3 tests/mod_editor/test_nfl2k5_screen_hooks.py` | 10 passed | 11.051 | 129,796* |
| `python3 tests/mod_editor/test_nfl2k5_screen_hooks_unicorn.py` | 10 passed | 23.807 | 138,504 |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_runtime.py` | 12 passed, 1 failed: inherited playlist replay | 69.764 | 159,908 |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 5 passed, 4 setup errors above | 107.427 | 250,480 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 1 passed, 4 setup errors above | 108.150 | 336,884 |
| `python3 tests/mod_editor/test_nfl2k5_screen_hooks_manifest.py` | 0 run, 1 setup error: stale parent manifest | 0.059 | 60,080 |

*Screen integrity ran in a timed sequential shell with the initial read-option
suite, so its RSS is the combined maximum. The initial read-option test exposed
the stale fixture; the final read-option row above is after the fixture fix.
The new suite's first run caught an incorrect test expectation that resealing
could bless nonzero initial RW. The assertion was corrected to expect the
allocator's existing refusal; production guards were not relaxed.

The six focused owner/controls suites total **68 passing tests**. Also passed:

```text
python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json
python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json --json
python3 tools/nfl2k5_read_option_runtime_assemble.py --check
python3 tools/nfl2k5_screen_hooks_assemble.py --check
python3 -m py_compile mod_editor/core/nfl2k5_read_option_runtime.py mod_editor/core/nfl2k5_screen_hooks.py tests/mod_editor/test_nfl2k5_read_option_screen_hooks_compose.py
git diff --check
python3 .scratch/readoption-screenhooks-compose-fix/inspect_union.py
```

## HYPOTHESIS and Noah's witness list

All existing experimental/off defaults and prior feature witness protocols
remain. Offline guard compatibility does not establish gameplay compatibility.
After the companion repair, regenerated manifest and green full gates:

1. Build disposable copies from one supported source, retaining receipts and
   hashes: read-option alone, screen hooks alone, both, then the intended full
   feature set. Cold boot each and enter Practice and Exhibition.
2. Compare ATL178 screen snaps with fixed rosters, defense, field position and
   control mode, including positive explicit QB delays and ordinary-pass
   controls. Check line release, QB timing, throw/catch, sacks and stalled tasks.
3. Run authored Shotgun zone-read hold/keep and release/give, then RPO B/X
   presses with ready/unready receivers and both field directions. Require one
   commitment, no lost input or duplicated transfer, normal throwing and a cue
   that clears after the mesh.
4. Alternate screen, RPO, ordinary pass and run across consecutive downs;
   repeat after audible, no-huddle, controller switch, substitution, turnover,
   save/reload and a new session. Check no leaked latch or altered ordinary QB
   timer/callback. Repeat human and CPU trials with the selected full stack.

## Resource and delivery discipline

Only this worktree was written. Retail XBE/resource reads and the Ghidra corpus
were read-only. No disc build, whole archive/disc RAM load or acceptance image
was created. Each measured process stayed below 337 MiB; root free space was
101 GiB. Scratch contains only scripts, logs, JSON and delivery metadata/bundle,
with no disc, pack or XBE copy. `ASTRA_BRIEF.md` and `.scratch/` are excluded
from the explicit delivery paths.

Direct explicit-path staging succeeded, so no bundle fallback is needed.
Delivery uses `git add <six explicit paths>` followed by
`git commit -- <the same six explicit paths>`: the two Python owners, their
focused composition test, the request fixture, this report and `WIRING.md`.
Commit identity, parent and exact changed-path verification are retained in
`.scratch/readoption-screenhooks-compose-fix/delivery.json` and the final
session reply. No push is performed. Full-stack gate acceptance remains
pending the separately assigned companion repair and manifest regeneration.
