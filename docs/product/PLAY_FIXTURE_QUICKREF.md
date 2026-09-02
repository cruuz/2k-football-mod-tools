# PLAY fixture quick-ref — 4 saves → 11-byte canvas

**Keep this page on second monitor during `harness --run`. No synthesis until checks pass.**

## 1) FILE — 3 min

| save | action on o0308 play0 WR1 slot0 | file delta expected (`vc_53450030/0:106803200` slice) | watchpoint target (guest RAM = `load_base+body_off+FIELD`) | draw vs exec label |
|------|----------------------------------|--------------------------------|---------------|---------------------|
| **FX** | move +2 X only | exactly one `i16` in `0x1A4-0x1E8` (`body_off+0x134+0x70 … +0xB4`, `formation0 @0x134`) flips `+2` LE, other `i16` stays `0` | `watch r <addr_of_that_i16> len 2` | fires on play-call draw → **X** |
| **FY** | move +2 Y only | exactly one *other* `i16` in same window flips `+2` | `watch r <addr_of_other_i16> len 2` | fires on draw → **Y** |
| **FW** | +1 waypoint, endpoints fixed | chain grows `+8` at `0x9aec` (new `NODE 8` after `0x9ae4 0b 06 TERM`), `FX/FY` bytes unchanged | `watch r 0x9aec len 8` | fires on draw iff FW loaded |
| **FT** | route-type flip, no move | `±0` bytes, one of `0x9ae4+2..7` flips, `FX/FY` stable | `watch r 0x9ae4+2..7 len 1 each` | flips style, stable in FX/FY → **style flag** |

Invariant trailer `ff07×N + 03000000 28000000` at tail of `0xB4`/`0x50` must **not** move in any of the four.

## 2) RUN — 12 min

```bash
bash tools/xemu_formation_fixture_harness.sh --run   # creates /tmp/xemu-2k5-fixture/{clean,FX,FY,FW,FT}
# in xemu headless on o0308 play0 WR1 slot0: do FX, save as FX; FY→FY; FW→FW; FT→FT; keep clean untouched
bash tools/xemu_formation_fixture_harness.sh --diff  # cmp -l on 0:106803200 + overlay on 0x70-0xB4 / NODE dump
```

If `FX xor FY` isolates one `i16` → note its `file_off` and `body_off+FIELD`.

## 3) PROVE — 15 min

```
# gdb path (this QEMU build has no 'watch' monitor cmd — use gdbserver)
xemu -gdb tcp::1234 …   # then: gdb → target remote :1234 → watch *0xADDR
# dump path
monitor: dump-guest-memory -p /tmp/guest.bin <paddr> <len>
# measure draw (highlight play0) vs exec (snap→WR runs)
```

Label only when orthogonal diff **and** consumer agree. Until then writer stays clone-only:
`mod_editor/core/nfl2k5_formation_play_writer.py` re-encodes 12 relative `i32` on `39→40/254→255`.

## 4) PAYLOAD — offline shape staked (no guess)

`NODE_BASE 0x9adc, NODE_SIZE 8, play0 chain 2×8: 0x9adc 1b 00 00 00 00 00 40 80 → 0x9ae4 0b 06 00 00 01 00 00 68 TERM` — proved by `tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --play 0 --slot 0 --dump-nodes` and `11 passed` pack-0 proof.

Repro: `bash tools/xemu_formation_fixture_harness.sh --check` prints the two `0xB4` hexdumps + `@0x245c/0x24ac` `0x50` invariant for overlay.
