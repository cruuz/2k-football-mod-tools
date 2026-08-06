# Formation coordinate offline variance — what xemu must confirm next

Offline data for `nfl2k5.resource.o0308.c0000.k504c4159` `0xB4 @0x134` (Split Pro) vs `0x1e8` (Split Twins) — `harness --check` dry-run is reproducible without xemu. `X/Y` still unlabelled.

## Exact diffs that survive scrutiny

- `0xB4[0x00-0x0C]` formation name pointer only (opaque, not a coordinate).
- `0xB4[0x70-0xB4]` variance: `uniq bytes 11-29` — this is the only region where offline `WR shift` would live. Raw for `clean` vs `shifted` (hex):
  - `a (Split Pro @0x134)`: header `60 8d 00 01` then `... 3d 86 37 82 5a 84 54 86 57 86 53 86 56 86 cd 86 b3 86 58 80 55 86 59 86 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 ff07 03000000 28000000`
  - `b (Split Twins @0x1e8)`: same trailer, header `3d 80 37 82 5e 84 5c 86 5f 86 5d 86 71 86 8e 86 7c 86 60 86 5b 86 61 86 d5 86 46 86 d6 86 ...`
  - Invariant: last 32 bytes (`ff07 × N + 03000000 28000000`) never move offline — so any `FX`/`FY` fixture that flips exactly one `i16` pair inside `0x70-0xB4` while leaving that trailer alone stakes `X` or `Y`.
- `0x50` aux at `0x245c` vs `0x24ac` (80 bytes): only bytes `0-27` vary (`37 82..` region), same invariant trailer — confirms aux is not the per-player 11×6.18 slot, but a related header.

## Why sign/scale/axis are still blocked

Corpus `uniq` alone cannot tell whether `0x86 37` is `i16 0x8637` or `u16` with bias, nor whether `+X` is east or west, nor whether units are inches vs `1/2` yard — need `FX +2 X` vs `FY +2 Y` on the same `WR1 slot 0` to get sign and axis (exactly one `i16` should step `+2` little-endian per move, the other must stay `0`), and the same `i16` must be read in xemu draw to confirm it is a visual coordinate not a flag/timing.

## Exact `harness --run` command to close

```
bash tools/xemu_formation_fixture_harness.sh --run   # isolated /tmp/xemu-2k5-fixture
bash tools/xemu_formation_fixture_harness.sh --diff  # cmp -l on vc_53450030/0:106803200 + overlay on 0x70-0xB4
# then, if FX xor FY isolates one i16:
xemu -monitor -watch r <addr-of-that-i16>  # draw vs exec
```

Until `FX xor FY` isolates one `i16` and watchpoint fires on draw, the field canvas cannot be turned into an authorable control — `formation_play_writer` stays clone-only for 2K5 `PLAY`.
