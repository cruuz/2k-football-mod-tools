#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

python3 -m py_compile tools/layout_inventory.py
tmp=$(mktemp -d /tmp/vc-layout-validate.XXXXXX)
trap 'rm -rf "$tmp"' EXIT

PYTHONPATH=tools python3 tools/layout_inventory.py \
  --apf-index 'extracted/All-Pro Football 2K8 (USA)/0A' \
  --nfl-index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --json "$tmp/layout.json" \
  --tsv "$tmp/layout.tsv"

cmp "$tmp/layout.json" reports/assets/cross_title_layout_inventory.json
cmp "$tmp/layout.tsv" reports/assets/cross_title_layout_records.tsv

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("reports/assets/cross_title_layout_inventory.json").read_text())
assert report["schema"] == "vc_cross_title_layout_inventory/v1"
summary = report["summary"]
assert summary == {
    "all_known_record_types_sized": True,
    "all_links_adjacent_and_bounded": True,
    "apf_distinct_record_name_count": 362,
    "apf_layout_count": 161,
    "apf_record_count": 1837,
    "apf_record_type_counts": {"0": 1228, "1": 72, "2": 180, "3": 357},
    "nfl_distinct_record_name_count": 213,
    "nfl_layout_count": 86,
    "nfl_record_count": 280,
    "nfl_record_type_counts": {"0": 180, "1": 23, "2": 77},
    "shared_casefolded_record_name_count": 59,
}
assert len(report["layouts"]) == 247
assert len(report["records"]) == 2117
assert len(report["shared_casefolded_record_names"]) == 59
assert "title_bar_wide" in report["shared_casefolded_record_names"]
assert "weekly_prep_home_a" in report["shared_casefolded_record_names"]
assert all(item["record_size"] in (0x30, 0x40, 0x60, 0x70) for item in report["records"])
assert all("PORTME:" in item for item in report["portme"])

xbe = Path("extracted/ESPN NFL 2K5 (USA)/default.xbe").read_bytes()
# In the XBE .text mapping, file offset = VA - 0x10000.
assert xbe[0x1591A0:0x1591AF] == bytes.fromhex(
    "6860911600ba4c415954b978b9bd00"
)
assert xbe[0x1590B0:0x1590C4] == bytes.fromhex(
    "8b41148b480485c974078d4c01038948048b4004"
)
assert xbe[0x5A8B3:0x5A8B8] == bytes.fromhex("ba4c415954")

apf_pseudo = "\n".join(
    path.read_text(errors="replace")
    for path in Path("research/functions/apf2k8/pseudo_c").glob("*.c")
)
assert apf_pseudo.lower().count("0x86a1ac9e") >= 8
assert "Function_84B16398" in apf_pseudo
PY

echo 'LAYOUT_INVENTORY_VALIDATION_PASS apf=161/1837 nfl=86/280 shared_names=59'
