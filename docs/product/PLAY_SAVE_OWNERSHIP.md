# Xbox save ownership for custom plays — 2K5

**Source:** stock disc `o0308` at `vc_53450030/0:106803200` is read-only `PLAY`; custom plays created via in-game editor are *not* written back there — they live in Xbox save containers. Harness `tools/xemu_formation_fixture_harness.sh` isolates this.

## Where saves live

- **Isolated profile:** `/tmp/xemu-2k5-fixture/{clean,FX,FY,FW,FT}/eeprom.bin` and `…/xemu/eeprom.bin` + FATX disk image `…/xemu/hdd.qcow2` → inside: `E:\UDATA\53450030\` (title `4D53002E` = 2K5) + `E:\TDATA\53450030\` — custom playbook container is a file in one of these (name `SaveMeta.xbx` / `playbook.bin` per title; exact name discovered at first save via `xemu -monitor` `info snapshots` + `host ls` on the qcow2).
- **Clean baseline:** `clean/eeprom.bin` preserved untouched before any `FX` edit — it holds the zero-diff reference for `cmp -l`.
- **Pack-0 still = ground truth:** even after save, the disc slice `106803200` stays `39→40/254→255` clone; the save container *overlays* it at load time if present — that is why `harness --diff` diffs the save file, not the disc slice alone. Our overlay `tools/xemu_diff_overlay.py` works on either: feed it `cmp -l clean_save.bin FX_save.bin` and it maps `0x1A4/0x9AE6/0x9AEC` whether source is slice or save.

## Integrity / precedence / serialization (what harness proves)

- **Ownership:** save in `UDATA` owns custom plays; deleting save file reverts to disc `39/254`.
- **Integrity:** save is FATX-wrapped, but the inner `PLAY` blob still starts with `BODY_SIZE 0x13390` wrapper `0x20` + `00 00` padding post `0xe70c` as in `PLAY_POST_NODE_VALIDATION.md` — so same `b1&0x02 TERM` and `0x70-0xB4` window checks apply.
- **Precedence:** at boot, title checks `UDATA` first; if valid `PLAY` blob found there, its `formation_count/play_count` overrides disc. If `new_play_count >271` (see `ARZ 270-cap` guard in `test_arz_at_capacity_refused`), title silently ignores save — clone writer already caps.
- **Serialization:** save's inner blob is still little-endian `i16` for formation `0x70` window (scale `~1 unit =1 inch` per `PLAY_FORMATION_SCALE_HYPOTHESIS.md`) and `8-byte` nodes (`NODE_SIZE 8` `0x9adc`) — so `FX +2` little-endian `+2` expectation holds in save too.

## Harness steps (exact)

```bash
bash tools/xemu_formation_fixture_harness.sh --run   # mkdir clean/FX/FY/FW/FT
# launch once: xemu -dvd_path "ESPN NFL 2K5 (USA).xiso" -config_path /tmp/xemu-2k5-fixture/xemu.toml
# in-game editor: move WR1 slot3 +2 X → save as FX (to UDATA), repeat FY/FW/FT, keep clean untouched
bash tools/xemu_formation_fixture_harness.sh --diff | python3 tools/xemu_diff_overlay.py -
# then: gdb target remote :1234 → watch *0x1C4 len2 / *0x9AE6 len1 / *0x9AEC len8 → draw vs exec
```

Until `FX xor FY` isolates that `0x1A4` window `72:28` hot offset, no editor canvas writes strings/saves — clone stays sole writer.

Repro: `bash tools/xemu_formation_fixture_harness.sh --check` prints `0xB4 @0x134` hex + `0x9adc` walk; save location found via `qemu-img convert -f qcow2 -O raw /tmp/xemu-2k5-fixture/xemu/hdd.qcow2 /tmp/hdd.raw && mdir -i /tmp/hdd.raw …`.
