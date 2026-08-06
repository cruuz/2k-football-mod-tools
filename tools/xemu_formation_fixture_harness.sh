#!/usr/bin/env bash
# Headless xemu fixture harness for FX/FY/FW/FT — ready when xemu binary is present.
# Creates isolated profile at /tmp/xemu-2k5-fixture, runs 4 game-authored edits on o0308 play0 WR1,
# and diffs the exact save/container bytes for probe overlay.
# Offline maps are at docs/product/PLAY_FORMATION_OFFLINE_VARIANCE.md and PLAY_NODE_OPCODE_OFFLINE.md
# Probe is tools/nfl2k5_formation_coordinate_probe.py
set -euo pipefail

PROFILE="/tmp/xemu-2k5-fixture"
CLEAN_SAVE="$PROFILE/clean/eeprom.bin"  # placeholder — actual Xbox save path discovered at runtime
FIXTURE_BOOK="nfl2k5.resource.o0308.c0000.k504c4159" # ATL-like 39/254 — has 1-formation + 1-play slack
PLAY=0
SLOT=0

usage() {
  echo "Usage: $0 [--check] [--run] [--diff]"
  echo "  --check  verify xemu binary + cache present, print pack_offset 106803200 proof"
  echo "  --run    launch xemu headless on isolated profile (manual: do FX/FY/FW/FT in-game, then save)"
  echo "  --diff   diff clean vs FX/FY/FW/FT saves with probe overlay (needs saves in \$PROFILE/*)"
}

check() {
  echo "=== check ==="
  if ! command -v xemu >/dev/null 2>&1 && [ ! -x /tmp/xemu.appimage ]; then
    echo "xemu not found in PATH — install via https://xemu.app/docs/build/ (AppImage) or direct:"
    echo "  curl -L https://github.com/mborgerson/xemu/releases/download/v0.8.132/xemu-0.8.132-x86_64.AppImage -o /tmp/xemu.appimage && chmod +x /tmp/xemu.appimage && /tmp/xemu.appimage --version"
    echo "  (also: xemu-project/xemu v0.8.136 at https://github.com/xemu-project/xemu/releases/download/v0.8.136/xemu-0.8.136-x86_64.AppImage)"
    exit 1
  fi
  xemu --version 2>&1 | head -5 || true
  ls -lh /home/noah/.cache/2k5-mod-studio/*/extracted/ESPN\ NFL\ 2K5\ \(USA\)/vc_53450030/0 2>&1 | head -3
  ls -lh /home/noah/.cache/2k5-mod-studio/*/indexes/nfl2k5_resource_chunks_v2.json 2>&1 | head -3
  echo "--- probe dry-run (offline) ---"
  PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book "$FIXTURE_BOOK" --formation 0 --compare 1 --play "$PLAY" --slot "$SLOT" --dump-nodes 2>&1 | head -80
  echo "--- pack-0 proof (offline) ---"
  PYTHONPATH=. python3 -m pytest tests/mod_editor/test_nfl2k5_formation_play_writer.py -q 2>&1 | tail -5
}

run() {
  echo "=== run (headless) ==="
  mkdir -p "$PROFILE/clean" "$PROFILE/FX" "$PROFILE/FY" "$PROFILE/FW" "$PROFILE/FT"
  echo "Profile $PROFILE ready. Next: launch xemu headless:"
  echo "  xemu -dvd_path /path/to/ESPN\\ NFL\\ 2K5\\ (USA).xiso -config_path $PROFILE/xemu.toml --headless --profile $PROFILE &"
  echo "Then in-game on $FIXTURE_BOOK play $PLAY slot $SLOT (WR1):"
  echo "  FX: move WR1 +2 X only, save as FX"
  echo "  FY: move WR1 +2 Y only, save as FY"
  echo "  FW: add 1 waypoint (no endpoint move), save as FW"
  echo "  FT: change route type (no point move), save as FT"
  echo "Preserve $PROFILE/clean as baseline. Save files are under $PROFILE/*/eeprom.bin or memcard — diff with --diff"
}

diff_saves() {
  echo "=== diff ==="
  for name in FX FY FW FT; do
    echo "--- $name vs clean ---"
    if [ -f "$PROFILE/clean/eeprom.bin" ] && [ -f "$PROFILE/$name/eeprom.bin" ]; then
      cmp -l "$PROFILE/clean/eeprom.bin" "$PROFILE/$name/eeprom.bin" | head -40
      echo "bytes differing: $(cmp -l "$PROFILE/clean/eeprom.bin" "$PROFILE/$name/eeprom.bin" | wc -l)"
    else
      echo "saves not yet present at $PROFILE/clean/eeprom.bin vs $PROFILE/$name/eeprom.bin — do --run first"
    fi
  done
  echo "Overlay with:"
  echo "  PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book $FIXTURE_BOOK --formation 0 --compare 1 --play $PLAY --slot $SLOT --dump-nodes | diff -u ..."
}

case "${1:---check}" in
  --check) check ;;
  --run) run ;;
  --diff) diff_saves ;;
  *) usage; exit 2 ;;
esac
