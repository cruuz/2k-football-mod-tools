#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

python3 -m py_compile tools/apf_txt_loc.py
tmp=$(mktemp -d /tmp/apf-txt-loc-validate.XXXXXX)
trap 'rm -rf "$tmp"' EXIT

PYTHONPATH=tools python3 tools/apf_txt_loc.py \
  'extracted/All-Pro Football 2K8 (USA)/0A' \
  --json "$tmp/apf_txt_localization.json" \
  --tsv "$tmp/apf_txt_localization.tsv"

cmp "$tmp/apf_txt_localization.json" reports/assets/apf_txt_localization.json
cmp "$tmp/apf_txt_localization.tsv" reports/assets/apf_txt_localization.tsv

PYTHONPATH=tools python3 - <<'PY'
import json
from pathlib import Path

import apf_txt_loc

report = json.loads(Path("reports/assets/apf_txt_localization.json").read_text())
assert report["schema"] == "apf2k8_txt_localization/v1"
summary = report["summary"]
assert summary["table_count"] == 2
assert summary["record_count"] == 1572
assert summary["ordinary_record_count"] == 1571
assert summary["control_record_count"] == 1
assert summary["all_ids_strictly_sorted_and_unique"]
assert summary["all_ordinary_references_bounded"]
assert summary["only_fallback_entries_unreferenced"]
assert summary["all_bodies_rebuild_byte_identically"]
assert all("PORTME:" in item for item in report["portme"])

identities = {
    (table["outer_index"], table["inner_index"]): (
        table["inner_name"], table["body_size"], table["record_count"],
        table["pool_entry_count"], table["control_record_count"],
    )
    for table in report["tables"]
}
assert identities == {
    (526, 0): ("credits_English", 30120, 747, 742, 0),
    (1127, 0): ("English", 17310, 825, 552, 1),
}

tables = apf_txt_loc.parse_archive(
    Path("extracted/All-Pro Football 2K8 (USA)/0A"), 64 * 1024 * 1024
)
assert all(apf_txt_loc.rebuild_table(table) == table["_body"] for table in tables)

pseudo = Path(
    "research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_04864_05119.c"
).read_text(errors="replace")
assert "Function_84761868" in pseudo
assert "param_2 == 0xe33e3b9c" in pseudo
assert "uVar1 = 0xffffffff84529448" in pseudo
assert "FUN_84761a08" in pseudo
assert "piVar2 = (int *)(param_1 + 8)" in pseudo

startup = Path(
    "research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_01536_01791.c"
).read_text(errors="replace")
assert "FUN_84b6bd60(0xffffffffe33e3b9c)" in startup
PY

echo 'APF_TXT_LOCALIZATION_VALIDATION_PASS tables=2 records=1572 ordinary=1571 control=1'
