#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TEMPORARY=$(mktemp -d)
trap 'rm -rf "$TEMPORARY"' EXIT

GAME_INDEX=/var/lib/flatpak/app/net.pcsx2.PCSX2/current/active/files/bin/resources/GameIndex.yaml
REDUMP_DB=/var/lib/flatpak/app/net.pcsx2.PCSX2/current/active/files/bin/resources/RedumpDatabase.yaml
CARD1=/home/noah/.var/app/net.pcsx2.PCSX2/config/PCSX2/memcards/Mcd001.ps2
CARD2=/home/noah/.var/app/net.pcsx2.PCSX2/config/PCSX2/memcards/Mcd002.ps2

before_game=$(stat --printf='%d:%i:%s:%Y:%Z' "$GAME_INDEX")
before_redump=$(stat --printf='%d:%i:%s:%Y:%Z' "$REDUMP_DB")
before_card1=$(stat --printf='%d:%i:%s:%Y:%Z' "$CARD1")
before_card2=$(stat --printf='%d:%i:%s:%Y:%Z' "$CARD2")

python3 "$ROOT/tools/nfl2k5_ps2_fixture_audit.py" \
  --json-out "$TEMPORARY/audit.json"
cmp "$TEMPORARY/audit.json" \
  "$ROOT/reports/gameplay_tuning/nfl2k5_ps2_fixture_availability.json"

PYTHONPATH="$ROOT/tools${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest tests.test_nfl2k5_ps2_fixture_audit

python3 - "$TEMPORARY/audit.json" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_ps2_fixture_audit/v1"
assert report["summary"] == {
    "all_four_ps2_owners_mapped": False,
    "expected_iso_present": False,
    "extracted_boot_elf_present": False,
    "memory_card_count": 2,
    "pcsx2_texture_dump_present": False,
    "safe_ps2_patch_ready": False,
    "save_directory_marker_present": False,
    "serial": "SLUS-20919",
}
assert report["target"]["expected_iso_md5"] == "46ef5e7a2e155994e7c3e5627293e068"
assert report["target"]["expected_iso_size"] == 4665081856
assert report["target"]["boot_elf_expected_name"] == "SLUS_209.19"
assert len(report["limitations"]) == 4
assert all(not row["address_reuse_from_xbox_allowed"] for row in report["limitations"])
assert all(not row["safe_ps2_patch_ready"] for row in report["limitations"])
assert all(
    row["classification"] == "xdvdfs_xbox"
    for row in report["local_evidence"]["rejected_named_disc_suspects"]
)
PY

test "$(stat --printf='%d:%i:%s:%Y:%Z' "$GAME_INDEX")" = "$before_game"
test "$(stat --printf='%d:%i:%s:%Y:%Z' "$REDUMP_DB")" = "$before_redump"
test "$(stat --printf='%d:%i:%s:%Y:%Z' "$CARD1")" = "$before_card1"
test "$(stat --printf='%d:%i:%s:%Y:%Z' "$CARD2")" = "$before_card2"

echo 'NFL2K5_PS2_FIXTURE_AUDIT_VALIDATION_PASS serial=SLUS-20919 iso=false elf=false save=false textures=false owners=0/4 xbox_addresses_reused=false sources_unchanged=true'
