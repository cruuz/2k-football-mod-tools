#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex_report='reports/headers/apf2k8_xex_report.json'
probe='reports/static_recomp/apf2k8_static_recomp_probe.json'
generated='build-static-recomp-apf/ppc-filtered'
shared="$generated/ppc_recomp_shared.h"
mapping="$generated/ppc_func_mapping.cpp"
report='reports/static_recomp/apf2k8_static_import_surface.json'
table='reports/static_recomp/apf2k8_static_import_surface.tsv'
doc='docs/research/apf_static_import_surface.md'

for required in "$xex_report" "$probe" "$shared" "$mapping" "$report" \
    "$table" "$doc" tools/apf_static_import_surface.py; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-static-import-surface.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_static_import_surface.py

python3 tools/apf_static_import_surface.py \
  --xex-report "$xex_report" \
  --static-probe "$probe" \
  --shared-header "$shared" \
  --mapping "$mapping" \
  --generated-dir "$generated" \
  --json "$temporary/report.json" \
  --tsv "$temporary/report.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/report.tsv" "$table"

python3 - "$report" "$table" "$doc" <<'PY'
import csv
import json
from pathlib import Path
import sys

report_path, table_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_static_import_surface/v1"
assert report["result"] == {
    "logical_import_count": 347,
    "callable_thunk_count": 334,
    "data_slot_count": 13,
    "callable_thunks_with_static_calls": 333,
    "callable_thunks_without_static_calls": 1,
    "generated_static_call_site_count": 1708,
    "all_callable_imports_implemented": False,
    "native_title_runtime_exists": False,
}
assert report["symbols_by_library"] == {"xam.xex": 177, "xboxkrnl.exe": 157}
assert report["call_sites_by_library"] == {"xam.xex": 351, "xboxkrnl.exe": 1357}
assert report["symbols_by_planning_lane"] == {
    "audio_voice": 13,
    "graphics_memory": 30,
    "input": 4,
    "kernel_crt_io_sync": 108,
    "loader_crypto": 10,
    "network": 91,
    "xam_system_profile_ui_or_other": 78,
}
assert report["call_sites_by_planning_lane"] == {
    "audio_voice": 17,
    "graphics_memory": 55,
    "input": 6,
    "kernel_crt_io_sync": 1274,
    "loader_crypto": 18,
    "network": 96,
    "xam_system_profile_ui_or_other": 242,
}
assert report["uncalled_callable_symbols"] == ["__imp____C_specific_handler"]
assert len(report["data_imports"]) == 13
assert [row["name"] for row in report["top_callable_imports"][:6]] == [
    "KfLowerIrql", "KeReleaseSpinLockFromRaisedIrql",
    "RtlLeaveCriticalSection", "RtlEnterCriticalSection",
    "KeRaiseIrqlToDpcLevel", "KeAcquireSpinLockAtRaisedIrql",
]

with table_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 347
assert sum(row["kind"] == "callable_thunk" for row in rows) == 334
assert sum(row["kind"] == "data_slot" for row in rows) == 13
assert sum(int(row["static_call_sites"]) for row in rows) == 1708
assert next(row for row in rows if row["name"] == "XamInputGetState")["static_call_sites"] == "1"
assert next(row for row in rows if row["name"] == "VdSwap")["static_call_sites"] == "1"
assert next(row for row in rows if row["name"] == "XMACreateContext")["static_call_sites"] == "1"

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking", "1,708",
    "334 callable", "13 imported data slots", "trap/no-op definition",
    "are not dynamic reachability",
    "APF_STATIC_IMPORT_SURFACE_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

echo 'APF_STATIC_IMPORT_SURFACE_VALIDATION_PASS logical=347 callable=334 data=13 called=333 sites=1708 runtime=no'
