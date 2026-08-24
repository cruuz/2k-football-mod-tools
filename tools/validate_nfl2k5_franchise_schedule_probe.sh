#!/usr/bin/env bash
# Deterministic validator for the franchise schedule probe.
#
# Always runs the probe's self-test (no game data required).  When the
# gitignored raw fixture artifacts/xemu-hdd-from-qcow2.raw is present it
# additionally parses the pinned pre-draft Franchise1 SAVEGAME.DAT in
# read-only mode and pins the discovered table offsets and the Super Bowl
# record.  The qcow2 itself is never opened or modified here.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile tools/nfl2k5_franchise_schedule_probe.py
python3 tools/nfl2k5_franchise_schedule_probe.py --self-test

RAW=artifacts/xemu-hdd-from-qcow2.raw
FRANCHISE_SHA256=0db746fe2c8ae2102fdd420863a5e5bcddec4b83ac3e234568824c337e4422a7
if [[ -f "$RAW" && ! -L "$RAW" ]]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  python3 tools/nfl2k5_franchise_schedule_probe.py \
    --image "$RAW" \
    --expected-sha256 "$FRANCHISE_SHA256" \
    --json-out "$tmp/probe.json" \
    --tsv-out "$tmp/probe.tsv" \
    | tee "$tmp/probe.log"
  grep -q "NFL2K5_FRANCHISE_SCHEDULE_PROBE_OK" "$tmp/probe.log"
  grep -q "upcoming@0x00072a94" "$tmp/probe.log"
  grep -q "played@0x000917ca" "$tmp/probe.log"
  grep -q "fixture=True" "$tmp/probe.log"
  grep -q "read_only=true" "$tmp/probe.log"
  python3 - "$tmp/probe.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
summary = report["summary"]
assert report["read_only"] is True
assert report["inputs"]["matches_pinned_predraft_fixture"] is True
assert summary["upcoming_games"] == 256
assert summary["played_games"] == 268
assert summary["upcoming_week_span"] == [1, 17]
sb = summary["super_bowl_game"]
assert sb["round"] == "super_bowl" and sb["week"] == 20
assert sb["offset"] == "0x0009228a"
assert sb["hour_field"] == 4 and sb["minute_field"] == 0
PY
  echo "NFL2K5_FRANCHISE_SCHEDULE_PROBE_FIXTURE_PASS"
else
  echo "NFL2K5_FRANCHISE_SCHEDULE_PROBE_SELF_TEST_ONLY (raw fixture absent)"
fi

echo "NFL2K5_FRANCHISE_SCHEDULE_PROBE_VALIDATION_PASS"
