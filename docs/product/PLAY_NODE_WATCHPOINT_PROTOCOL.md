# Node opcode watchpoint — exact offline bytes to stake before live

Source: same `o0308` `c0000.k504c4159` body. This bridges `PLAY_NODE_OPCODE_PAYLOAD_HYPOTHESIS.md` to an xemu command without guessing the chain grammar.

## Stake bytes (offline, byte-exact)

- Chain for play 0 slot 0 (descriptor `0xb11022`, `chain_start=0`) is 2 nodes at fixed offsets:
  - `0x9adc`: `1b 00 00 00 00 00 40 80`  (`b0=0x1b` open, `b1=0x00` not `TERM`)
  - `0x9ae4`: `0b 06 00 00 01 00 00 68`  (`b0=0x0b` close, `b1=0x06` ⇒ `b1&0x02 TERM`)
  - Post-chain: `0x9aec` onward is the next play header (not free-pool, proved by repacking holding).
- `0x50` aux (per-formation extra, 80 bytes, 3× at `0x240c/0x245c/0x24ac`): offline variance shows only header/shift bytes vary (`uniq 11-29` in `0x70-0xB4` overlap), trailing `ff07.. ff07 03000000 28000000` is invariant — so `FW` growth must be in node chain, not aux, if our 8-byte-node hypothesis is right.

## Watchpoint plan (do not author chain before this)

1. `monitor` watchpoints, read-access, on the exact stale-file bytes that `FW`/`FT` are predicted to touch:
   - `watch r 0x9ae4+2 .. 0x9ae4+7` (operand bytes of the closing `0x0b` node): `FT` should fault here, `FX`/`FY` must not.
   - `watch r 0x9aec .. 0x9af3` (the would-be third node if `FW` inserts one 8-byte node): read during play-call draw iff `FW` variant is loaded.
   - `watch r 0x70+off .. 0x70+off+1` only after `FX xor FY` shows `+2`/`-2` linear step on the same `i16` — that offset gets staked as `X` or `Y`.
2. Measure draw (play-call UI highlights play 0) vs exec (snap, WR runs route): a byte that fires in draw is a visual coordinate, a byte that fires only in exec is a timing/control flag — label accordingly.
3. `harness --run` saves are per-slot diffs on `vc_53450030/0:106803200` — keep them, `cmp -l` them offline, then re-load each save headless with watchpoints to close the loop.

## Repro (offline, no byte difference skipped)

```
# Confirm the two-node shape byte-for-byte
PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --play 0 --slot 0 --dump-nodes
# Extract the exact chain slice for watchpoint addresses
python3 -c "import pathlib; p=pathlib.Path('reports/specs/nfl2k5_playbook_resource_spec.json'); print(p.exists())"
```

No new chain writer is added here — formation/play import stays clone-only (`mod_editor/core/nfl2k5_formation_play_writer.py` re-encodes 12 relative i32 on a proved empty slot `39→40/254→255`).
