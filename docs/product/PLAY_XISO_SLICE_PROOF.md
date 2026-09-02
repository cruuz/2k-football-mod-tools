# XISO slice proof — StudioSession → canonical → pack-0 patch (offline, no xemu)

**Source:** `nfl2k5.resource.o0308.c0000.k504c4159` (ATL-like 39 formations / 254 plays, `0x13390` body). Proved at `pack_offset 106803200` in `vc_53450030/0`.

**What this proves (offline):** The Create Formation/Play buttons in the editor already flow through the real build pipeline, without xemu.

## Path

```
PlaybooksPanel [Create Formation/Play] 
  → StudioSession.create_formation/create_play (clone of donor, re-encodes 12 relative i32 pointers)
  → Facade.create_formation/create_play 
  → StudioSession.canonical_document() emits { kind: "play_formation_create" | "play_create", asset_id, donor_*_index }
  → Nfl2k5BuildService.build() → tools/nfl2k5_visual_mod_project.py
       → groups by asset_id → formation_play_adapter.build_unified_formation_play_import
       → compile_formation_play_creations (bumps counts at +0x34/+0x38, clones 0xB4+0x50 / 0x60+11 ptrs, checks 50/270 caps)
       → writes single pack-0 slice at vc_53450030/0:pack_offset 106803200 (size 0x20+0x13390)
  → verify reparses with parse_playbook_resource, asserts new names/links unchanged
```

## Pack-0 proof (no XISO copy needed)

```
PYTHONPATH=. python3 -m pytest tests/mod_editor/test_nfl2k5_formation_play_writer.py -q
# 3 tests: ATL 39→40/254→255 (+55 owned changed_ranges), ARZ 270-cap refusal, roundtrip
```

- `o0308` donor 0 formation + donor 0 play → `39→40` formations, `254→255` plays, `pack_offset 106803200`, 55 changed_ranges all inside `{+0x34,+0x38, dst 0xB4, dst 0x50, dst 0x60}` owned bytes.
- `o0307` ARZ at 270 plays correctly refuses with `That would need 271 plays but the PLAY capacity is 270`.

This is the same code path a full `Nfl2k5BuildService.build()` XISO uses — it just copies the user's 6.3 GB XISO and patches that one slice. The new slice is already verified without needing a 6.3 GB copy in CI.

## What still needs xemu

- Live save diff for `FX/FY/FW/FT` to map each `0xB4` byte in `0x70-0xB4` to `X`/`Y`/`orient` and each `NODE 8-byte` operand to `coord` vs `style` (probe `tools/nfl2k5_formation_coordinate_probe.py` + harness `tools/xemu_formation_fixture_harness.sh --check/--run/--diff` are ready).
- Read watchpoints while the play is drawn (play-call UI) vs executed (on-field) to confirm the same bytes are consumed.
- Then a full `Nfl2k5BuildService.build()` to `/tmp/atl-formation-play.xiso` and headless `xemu -dvd_path /tmp/atl-formation-play.xiso` screenshot proving the new formation/play slot appears in the in-game picker. That screenshot is the 100% gate.

## Repro (offline, 30s)

```
PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --formation 0 --compare 1 --play 0 --slot 0 --dump-nodes | head -40
PYTHONPATH=. python3 -m pytest tests/mod_editor/test_nfl2k5_formation_play_writer.py tests/mod_editor/test_nfl2k5_playbook_inspector.py tests/mod_editor/test_nfl2k5_playbook_route_writer.py -q
bash tools/xemu_formation_fixture_harness.sh --check 2>&1 | head -20
```

No retail bytes are checked in — only offsets, counts, and `sha256` sidecars.

## Next

Run `tools/xemu_formation_fixture_harness.sh --run` once xemu AppImage is at `/usr/local/bin/xemu`, then overlay the 4 save diffs on `docs/product/PLAY_FORMATION_OFFLINE_VARIANCE.md` and `PLAY_NODE_OPCODE_OFFLINE.md`.
