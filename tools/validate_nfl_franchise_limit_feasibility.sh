#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d /tmp/nfl-franchise-limit-feasibility.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

XBE="$ROOT/extracted/ESPN NFL 2K5 (USA)/default.xbe"
XBE_BEFORE="$(sha256sum "$XBE" | cut -d' ' -f1)"

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_nfl_franchise_limit_feasibility -v

PYTHONDONTWRITEBYTECODE=1 python3 \
  "$ROOT/tools/nfl_franchise_limit_feasibility.py" \
  --json-out "$TMP/report.json" --tsv-out "$TMP/report.tsv"

cmp "$TMP/report.json" \
  "$ROOT/reports/gameplay_tuning/nfl_franchise_limit_feasibility.json"
cmp "$TMP/report.tsv" \
  "$ROOT/reports/gameplay_tuning/nfl_franchise_limit_feasibility.tsv"

XBE_AFTER="$(sha256sum "$XBE" | cut -d' ' -f1)"
test "$XBE_BEFORE" = "$XBE_AFTER"
test "$XBE_AFTER" = \
  "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"

python3 - "$ROOT" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
report = json.loads((root / "reports/gameplay_tuning/nfl_franchise_limit_feasibility.json").read_text())
assert report["schema"] == "nfl2k5_franchise_limit_feasibility/v1"
assert len(report["matrix"]) == 5
assert report["summary"]["archive_only_fix_count"] == 0
assert report["summary"]["current_safe_writer_count"] == 0
assert report["platform_boundary"]["xbox_virtual_addresses_transfer_to_ps2"] is False
doc = (root / "docs/research/nfl_franchise_limit_feasibility.md").read_text()
for needle in (
    "Draft priority is the closest target",
    "`0x002BF950..0x002BF980`",
    "mode `9`, week `0x14`",
    "PS2 ELF",
    "not an archive-only fix",
):
    assert needle in doc, needle
PY

echo "NFL_FRANCHISE_LIMIT_FEASIBILITY_VALIDATION_PASS rows=5 archive_writers=0 safe_writers=0 platform=xbox pcsx2_offsets=false originals_unchanged=true"
